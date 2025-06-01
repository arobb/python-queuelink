# -*- coding: utf-8 -*-
"""Custom queue-pipe adapter to read from thread-safe queues and write their
contents to a pipe"""
from __future__ import unicode_literals

import io
import os
import logging

from queue import Empty
from os import PathLike
from typing import Union, get_args

from .contentwrapper import ContentWrapper
from .queue_handle_adapter_base import MessageCounter
from .queue_handle_adapter_base import _QueueHandleAdapterBase
from .timer import Timer
from .common import (
    safe_get,
    UNION_SUPPORTED_EVENTS,
    UNION_SUPPORTED_LOCKS,
    UNION_SUPPORTED_QUEUES,
    DIRECTION,
    UNION_SUPPORTED_IO_TYPES,
    UNION_SUPPORTED_PATH_TYPES)


# Private class only intended to be used by ProcessRunner
# Works around (https://bryceboe.com/2011/01/28/
# the-python-multiprocessing-queue-and-large-objects/ with large objects)
# by using ContentWrapper to buffer large lines to disk
class QueueHandleAdapterWriter(_QueueHandleAdapterBase):
    """Custom manager to read messages from a queue and write them to a file or pipe
    """
    def __init__(self,
                 queue: UNION_SUPPORTED_QUEUES,
                 *,  # End of positional arguments
                 handle: UNION_SUPPORTED_IO_TYPES=None,
                 name: str=None,
                 log_name: str=None,
                 start_method: str=None,
                 thread_only: bool=None,
                 trusted: bool=False):
        """Custom manager to read messages from a queue and write them to a file or pipe

        Args:
            queue: Queue to retrieve messages from
            handle: File name, handle, or pipe to write messages to
            name: Optional name for this reader
            log_name: Optional name for this reader in log lines
            start_method: Explicit multiprocessing start method to use
            thread_only: Force the adapter to use a thread rather than process
            trusted: Whether to trust Connection objects; True uses .send/.recv, False
                send_bytes/recv_bytes when reading from multiprocessing.connection.Connections
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
                             handle: UNION_SUPPORTED_IO_TYPES,
                             queue: UNION_SUPPORTED_QUEUES,
                             queue_lock: UNION_SUPPORTED_LOCKS,
                             stop_event: UNION_SUPPORTED_EVENTS,
                             messages_processed: MessageCounter,
                             trusted: bool,
                             **kwargs):
        """Copy lines from a local multiprocessing.JoinableQueue into a pipe

        Runs in a separate process, started by __init__. Does not close an open
        pipe or handle when done writing.

        Args:
            name: Name to use in logging
            handle: Handle/pipe/path to write to
            queue: Queue to write to
            queue_lock: Lock used to indicate a write is in progress
            stop_event: Used to determine whether to stop the process
            messages_processed: Number of elements moved from the queue to handle
            trusted: Whether to trust Connection objects
        """
        def open_location(location: Union[str, PathLike], line) -> \
                [io.TextIOWrapper, io.BufferedWriter]:
            """Open a location string/Path and return a normal IO handle."""
            if hasattr(line, 'decode'):
                # Open the output file in binary mode
                return open(location, mode='w+b')

            # Otherwise open as a text file
            return open(location, mode='w+')  # pylint: disable=unspecified-encoding

        def flush(file_handle):
            """Simple function to push content to disk"""
            if hasattr(file_handle, 'flush'):
                file_handle.flush()

            if hasattr(file_handle, 'fileno'):
                os.fsync(file_handle.fileno())

        log = logging.getLogger(f'{__name__}.queue_handle_adapter.{name}')
        log.addHandler(logging.NullHandler())

        log.info('Starting writer process')
        if hasattr(handle, 'closed') and handle.closed:
            log.warning('Handle is already closed')

        else:
            flush_timer = Timer(interval=1)  # Flush to disk at least once a second

            # Make comparisons easier/faster when checking for an open file
            # get_args syntax used for Python 3.8-3.12 compatibility https://stackoverflow.com/a/64643971
            handle_ready = True
            if isinstance(handle, get_args(UNION_SUPPORTED_PATH_TYPES)):
                handle_name = handle
                handle_ready = False

            # Handle type
            is_handle_bin = None

            # Loop over available lines until asked to stop
            while True:
                try:
                    line = safe_get(queue, timeout=0.05, stop_event=stop_event)

                    # Extract the content if the line is in a ContentWrapper
                    if line is not None:
                        content = line.value if isinstance(line, ContentWrapper) else line
                        is_content_bin = hasattr(content, 'decode')

                        # Lazily open the file handle if it is not already open
                        if not handle_ready:
                            handle = open_location(handle_name, line)  # pylint: disable=possibly-used-before-assignment
                            handle_ready = True

                        # Determine if the handle is binary
                        is_handle_bin = 'b' in handle.mode

                        # Write content into the file
                        log.info('Writing line to %s', name)
                        if is_handle_bin:
                            handle.write(content if is_content_bin else content.encode('utf-8'))
                        else:
                            handle.write(content.decode('utf-8') if is_content_bin else content)

                    # Indicate we finished processing a record
                    messages_processed.increment()

                    # Signal to the queue that we are done processing the line
                    if hasattr(queue, 'task_done'):
                        queue.task_done()

                    # Flush the pipe to make sure it gets to the process
                    if flush_timer.interval():
                        flush(handle)

                    # Exit if we are asked to stop
                    if stop_event.is_set():
                        log.info("Writer asked to stop")
                        break

                except Empty:
                    log.debug("No line currently available for %s", name)

                    # Exit if we are asked to stop
                    if stop_event.is_set():
                        log.info("Writer asked to stop")
                        break

        # Do a final flush
        flush(handle)

        # Close the handle if we opened it
        if 'handle_name' in locals() and hasattr(handle, 'close'):
            handle.close()

        # A bit of info
        log.info('Writer wrote %d messages', messages_processed.value)

        # Clean up references
        # Prevent "UserWarning: ResourceTracker called reentrantly for resource cleanup,
        # which is unsupported. The semaphore object '/<name>' might leak."
        queue_lock = None
        stop_event = None
        messages_processed = None

        log.info("Writer sub-process complete")
