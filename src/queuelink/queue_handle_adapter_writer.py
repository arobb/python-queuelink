# -*- coding: utf-8 -*-
"""Custom queue-pipe adapter to read from thread-safe queues and write their
contents to a pipe"""
from __future__ import unicode_literals

import io
import logging

from queue import Empty
from os import PathLike
from typing import Union, IO

from .contentwrapper import ContentWrapper
from .queue_handle_adapter_base import MessageCounter
from .queue_handle_adapter_base import _QueueHandleAdapterBase
from .timer import Timer
from .common import (
    safe_get,
    UNION_SUPPORTED_EVENTS,
    UNION_SUPPORTED_LOCKS,
    UNION_SUPPORTED_QUEUES,
    DIRECTION)


# Private class only intended to be used by ProcessRunner
# Works around (https://bryceboe.com/2011/01/28/
# the-python-multiprocessing-queue-and-large-objects/ with large objects)
# by using ContentWrapper to buffer large lines to disk
class QueueHandleAdapterWriter(_QueueHandleAdapterBase):
    """Custom pipe manager to read thread-safe queues and write their contents
        to an outbound pipe.

       Clients register their own queues.
    """
    UNION_SUPPORTED_WRITER_TYPES = Union[IO, str, PathLike]

    def __init__(self,
                 queue: UNION_SUPPORTED_QUEUES,
                 *,  # End of positional arguments
                 handle: UNION_SUPPORTED_WRITER_TYPES=None,
                 name: str=None,
                 log_name: str=None,
                 start_method: str=None,
                 thread_only: bool=None,
                 trusted: bool=False):
        """
        Args:
            handle (pipe): Pipe to write records to
        """
        # Initialize the parent class
        super().__init__(queue=queue,
                         subclass_name=__name__,
                         queue_direction=DIRECTION.TO,
                         name=name,
                         handle=handle,
                         log_name=log_name,
                         start_method=start_method,
                         thread_only=thread_only,
                         trusted=trusted)

    @staticmethod
    def queue_handle_adapter(*,  # All named parameters are required keyword arguments
                             name: str,
                             handle: io.IOBase,
                             queue: UNION_SUPPORTED_QUEUES,
                             queue_lock: UNION_SUPPORTED_LOCKS,
                             stop_event: UNION_SUPPORTED_EVENTS,
                             messages_processed: MessageCounter,
                             trusted: bool,
                             **kwargs):
        """Copy lines from a local multiprocessing.JoinableQueue into a pipe

        Runs in a separate process, started by __init__. Does not close the
        pipe when done writing.

        Args:
            name: Name to use in logging
            handle: Handle/pipe/path to write to
            queue: Queue to write to
            queue_lock: Lock used to indicate a write in progress
            stop_event: Used to determine whether to stop the process
            trusted: Whether to trust Connection objects
        """
        def open_location(location: Union[str, PathLike]):
            """Open a location string/Path and return a normal IO handle."""
            if hasattr(line, 'decode'):
                # Open the output file in binary mode
                return open(location, mode='w+b')

            # Otherwise open as a text file
            return open(location, mode='w+')  # pylint: disable=unspecified-encoding

        log = logging.getLogger(f'{__name__}.queue_handle_adapter.{name}')
        log.addHandler(logging.NullHandler())

        log.info('Starting writer process')
        if hasattr(handle, 'closed') and handle.closed:
            log.warning('Handle is already closed')

        else:
            flush_timer = Timer(interval=1)  # Flush to disk at least once a second

            # Make comparisons easier/faster when checking for an open file
            handle_ready = True
            if isinstance(handle, (str, PathLike)):
                handle_name = handle
                handle_ready = False

            # Loop over available lines until asked to stop
            while True:
                try:
                    line = safe_get(queue, timeout=0.05, stop_event=stop_event)

                    # Extract the content if the line is in a ContentWrapper
                    if line is not None:
                        content = line.value if isinstance(line, ContentWrapper) else line

                        # Lazily open the file handle if it is not already open
                        if not handle_ready:
                            handle = open_location(handle_name)  # pylint: disable=possibly-used-before-assignment
                            handle_ready = True

                        # Write content into the file
                        log.info('Writing line to %s', name)
                        handle.write(content)

                    # Indicate we finished processing a record
                    messages_processed.increment()

                    # Signal to the queue that we are done processing the line
                    if hasattr(queue, 'task_done'):
                        queue.task_done()

                    # Flush the pipe to make sure it gets to the process
                    if flush_timer.interval():
                        handle.flush()

                    # Exit if we are asked to stop
                    if stop_event.is_set():
                        log.info("Asked to stop")
                        break

                except Empty:
                    log.debug("No line currently available for %s", name)

                    # Exit if we are asked to stop
                    if stop_event.is_set():
                        log.info("Asked to stop")
                        break

        # Do a final flush
        if hasattr(handle, 'flush'):
            handle.flush()

        # Close the handle if we opened it
        if 'handle_name' in locals():
            handle.close()

        # Clean up references
        # Prevent "UserWarning: ResourceTracker called reentrantly for resource cleanup,
        # which is unsupported. The semaphore object '/<name>' might leak."
        queue_lock = None
        stop_event = None
        messages_processed = None

        log.info("Sub-process complete")
