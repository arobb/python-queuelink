# -*- coding: utf-8 -*-
"""Custom queue-pipe adapter to read from thread-safe queues and write their
contents to a pipe"""
from __future__ import unicode_literals

import enum
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


def _is_binary_handle(handle) -> bool:
    """Return True if *handle* is opened in binary mode.

    Prefers the io class hierarchy (works for io.BytesIO, io.BufferedWriter,
    io.StringIO, io.TextIOWrapper, etc.).  Falls back to inspecting the
    underlying ``.file`` attribute for wrapper objects such as
    ``tempfile._TemporaryFileWrapper`` that delegate to a standard io type
    but are not subclasses of it themselves.  As a last resort, checks the
    ``.mode`` attribute (reliable for standard file wrappers).
    """
    # Direct io hierarchy: most reliable
    if isinstance(handle, (io.RawIOBase, io.BufferedIOBase)):
        return True
    if isinstance(handle, io.TextIOBase):
        return False
    # Wrapper objects (e.g. _TemporaryFileWrapper): inspect the inner file
    inner = getattr(handle, 'file', None)
    if inner is not None:
        return isinstance(inner, (io.RawIOBase, io.BufferedIOBase))
    # Last resort: .mode attribute (standard for file-like wrappers)
    mode = getattr(handle, 'mode', None)
    if mode is not None:
        return 'b' in mode
    # Cannot determine — assume text
    return False


class WriteMode(enum.Enum):
    """Declared write mode for a path-based handle opened by ``QueueHandleAdapterWriter``.

    When passed as the ``write_mode`` argument, the handle is opened in the
    declared mode rather than inferring from the first line written.  This
    removes the non-deterministic first-line dependency and prevents unexpected
    ``TypeError`` failures if producers enqueue mixed-type content.

    ``BINARY``: open in binary mode (``w+b``); all enqueued lines must be ``bytes``.
    ``TEXT``: open in text mode (``w+``); all enqueued lines must be ``str``.

    When ``write_mode`` is omitted, the adapter infers the mode from the first
    line dequeued (``bytes`` → binary, ``str`` → text).  All subsequent lines
    must be the same type; a mismatch logs an error and raises ``TypeError``.

    Has no effect when ``handle`` is already an open file object — the mode of
    a pre-opened handle is determined by ``isinstance`` check at start time.
    """
    BINARY = 'binary'
    TEXT = 'text'


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
                 trusted: bool=False,
                 write_mode: WriteMode=None):
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
            write_mode: Declared binary/text mode for path-based handles.  When
                provided, the handle is opened in this mode rather than inferring
                from the first line.  Has no effect when ``handle`` is already an
                open file object.  See :class:`WriteMode`.
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
                         trusted=trusted,
                         write_mode=write_mode)

    @staticmethod
    def queue_handle_adapter(*,  # All named parameters are required keyword arguments
                             name: str,
                             handle: UNION_SUPPORTED_IO_TYPES,
                             queue: UNION_SUPPORTED_QUEUES,
                             queue_lock: UNION_SUPPORTED_LOCKS,
                             stop_event: UNION_SUPPORTED_EVENTS,
                             messages_processed: MessageCounter,
                             trusted: bool,
                             write_mode: WriteMode=None,
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
            write_mode: Declared binary/text mode for path-based handles
        """
        def open_location(location: Union[str, PathLike],
                          line,
                          mode: WriteMode) -> Union[io.TextIOWrapper, io.BufferedWriter]:
            """Open a location string/Path and return a normal IO handle.

            When *mode* is provided it takes precedence over first-line inference.
            """
            if mode is WriteMode.BINARY:
                return open(location, mode='w+b')

            if mode is WriteMode.TEXT:
                return open(location, mode='w+')  # pylint: disable=unspecified-encoding

            # No mode declared: infer from the first line's type.
            if hasattr(line, 'decode'):
                return open(location, mode='w+b')

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
            # get_args syntax used for Python 3.8-3.12 compatibility
            #   https://stackoverflow.com/a/64643971
            handle_ready = True
            is_handle_bin = None

            if isinstance(handle, get_args(UNION_SUPPORTED_PATH_TYPES)):
                handle_name = handle
                handle_ready = False
            else:
                # Pre-opened handle: determine binary mode once, before the loop.
                # File mode is immutable once opened, so this never needs re-reading.
                is_handle_bin = _is_binary_handle(handle)

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
                            handle = open_location(handle_name, line, write_mode)  # pylint: disable=possibly-used-before-assignment
                            handle_ready = True
                            # Determine binary mode once, immediately after open.
                            # open() always returns a standard io type, so isinstance
                            # is reliable here. Set once; never re-read in the loop.
                            is_handle_bin = isinstance(handle, (io.RawIOBase, io.BufferedIOBase))

                        # Guard against mixed-type streams.  Log the error for
                        # diagnostics, then re-raise so the caller can detect the
                        # failure via is_alive() or process exit code.
                        if is_handle_bin and not is_content_bin:
                            exc = TypeError(
                                'Handle opened in binary mode but received a str line. '
                                'All lines must be the same type.')
                            log.error('Mixed-type stream: %s', exc)
                            raise exc

                        if not is_handle_bin and is_content_bin:
                            exc = TypeError(
                                'Handle opened in text mode but received a bytes line. '
                                'All lines must be the same type.')
                            log.error('Mixed-type stream: %s', exc)
                            raise exc

                        # Write content into the file
                        # Direct encode/decode: content is already str or bytes here.
                        # No surrogate handling needed; use stdlib directly.
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
