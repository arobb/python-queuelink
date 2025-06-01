# -*- coding: utf-8 -*-
"""Custom pipe-queue adapter to read from a pipe and write *text* content to
thread-safe queues"""
from __future__ import unicode_literals

import codecs
import logging
import multiprocessing  # For comparisons

from typing import get_args

from .queue_handle_adapter_base import MessageCounter
from .queue_handle_adapter_base import _QueueHandleAdapterBase
from .contentwrapper import (
    get_len,
    ContentWrapper,
    WRAP_WHEN,
    conditional_wrap)
from .common import (
    UNION_SUPPORTED_EVENTS,
    UNION_SUPPORTED_LOCKS,
    UNION_SUPPORTED_QUEUES,
    DIRECTION,
    UNION_SUPPORTED_IO_TYPES,
    UNION_SUPPORTED_PATH_TYPES)

def connection_readline(self):
    """A readline method for multiprocessing.connection.Connection objects

    Also requires:
        An Event be applied as stop_event to know when to stop.
        A boolean as "self.trusted" to use recv_bytes vs recv

    conn_obj.readline = connection_wrapper.__get__(conn_obj)
    """
    while True:
        try:
            if self.stop_event.is_set():
                return None

            if self.poll(0.005):
                if self.trusted:
                    received = self.recv()
                else:
                    received = self.recv_bytes()

                return received

        except EOFError:
            return None

        except OSError as e:
            # Bad file descriptor / handle is closed
            if e.errno == 9 or str(e).lower() == 'handle is closed':
                return None

            # Some other OS error
            raise e

def add_methods_to_connections(conn: multiprocessing.connection.Connection,
                               trusted: bool) -> multiprocessing.connection.Connection:
    """Attach a new method and attributes to an existing object.

    Args:
        conn: A multiprocessing connection object.
        trusted: Whether to 'trust' the connection.

    Returns:
        The ``conn`` object with added methods and attributes.
    """
    if isinstance(conn, multiprocessing.connection.Connection):
        # Use the "descriptor protocol" to bind the method to an existing object
        # https://docs.python.org/3.13/howto/descriptor.html
        # https://stackoverflow.com/a/2982
        conn.readline = connection_readline.__get__(conn)
        conn.flush = lambda: None
        conn.trusted = trusted

    return conn


# Works around (https://bryceboe.com/2011/01/28/
# the-python-multiprocessing-queue-and-large-objects/ with large objects)
# by using ContentWrapper to buffer large lines to disk when wrap_when is always or auto
class QueueHandleAdapterReader(_QueueHandleAdapterBase):
    """Custom manager to capture the output of processes and store them in
    one more dedicated thread-safe or process-safe queues.
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
                 wrap_when: WRAP_WHEN=WRAP_WHEN.NEVER,
                 wrap_threshold: int=None):
        """
        Read lines of text from a handle or pipe and write (line by line) into a queue.

        Launches a new thread or process to perform the reading/putting. Prefers a new process,
        but if the provided queue is from `queue` will switch to using a thread.

        Args:
            queue: Queue to write to
            handle: An open handle or pipe to consume from
            name: Optional name for this reader
            log_name: Optional name for this reader in log lines
            start_method: Explicit multiprocessing start method to use
            thread_only: Force the adapter to use a thread rather than process
            trusted: Whether to trust Connection objects; True uses .send/.recv, False
                send_bytes/recv_bytes when reading from multiprocessing.connection.Connections
            wrap_when: When to use a ContentWrapper to encapsulate records
            wrap_threshold: Size limit for a line before it is wrapped in a ContentWrapper;
                only applies when wrap_when is WRAP_WHEN.AUTO
        """
        # A multiprocessing.Pipe (Connection) does not have a readline method
        # This checks the type. If not a Connection instance, it returns unchanged
        handle = add_methods_to_connections(conn=handle, trusted=trusted)

        # Check if we can use the pipe directly
        # IO type that does not have readline, and is not a file path
        # get_args syntax used for Python 3.8-3.12 compatibility https://stackoverflow.com/a/64643971
        if not hasattr(handle, 'readline') and \
          not isinstance(handle, get_args(UNION_SUPPORTED_PATH_TYPES)):
            original_handle = handle
            handle = codecs.getreader('utf-8')(original_handle)

        # Initialize the parent class
        # pylint: disable=bad-super-call
        # Py3 supports super().__init__; this form is kept for backward compat
        super().__init__(queue=queue,
                                         subclass_name=__name__,
                                         queue_direction=DIRECTION.FROM,
                                         name=name,
                                         handle=handle,
                                         log_name=log_name,
                                         start_method=start_method,
                                         thread_only=thread_only,
                                         trusted=trusted,
                                         wrap_when=wrap_when,
                                         wrap_threshold=wrap_threshold)

    # pylint: disable=arguments-differ
    @staticmethod
    def queue_handle_adapter(*,  # All named parameters are required keyword arguments
                             name: str,
                             handle: UNION_SUPPORTED_IO_TYPES,
                             queue: UNION_SUPPORTED_QUEUES,
                             queue_lock: UNION_SUPPORTED_LOCKS,
                             stop_event: UNION_SUPPORTED_EVENTS,
                             messages_processed: MessageCounter,
                             trusted: bool,
                             wrap_when: WRAP_WHEN,
                             wrap_threshold: int):
        """Copy lines from a given pipe handle into a local threading.Queue

        Runs in a separate process, started by __init__. Closes pipe when done
        reading.

        Args:
            name: Name to use in logging
            handle: Handle/pipe/path to read from
            queue: Queue to write to
            queue_lock: Lock used to indicate a write in progress
            stop_event: Used to determine whether to stop the process
            trusted: Whether to trust Connection objects
            wrap_when: When to use a ContentWrapper
            wrap_threshold: Size limit for a line before it is wrapped in a ContentWrapper
        """
        logger_name = f'{__name__}.queue_handle_adapter.{name}'
        log = logging.getLogger(logger_name)
        log.addHandler(logging.NullHandler())

        # Add readline and flush again; needed for spawn and forkserver start_methods
        handle = add_methods_to_connections(conn=handle, trusted=trusted)

        # Open the handle is it is a path
        # get_args syntax used for Python 3.8-3.12 compatibility https://stackoverflow.com/a/64643971
        handle_name = None
        if isinstance(handle, get_args(UNION_SUPPORTED_PATH_TYPES)):
            handle_name = handle
            handle = open(handle_name, 'r')

        # Calculate the threshold to use
        wrap_threshold = ContentWrapper.THRESHOLD if wrap_threshold is None else wrap_threshold

        # If its a Connection attach the stop_event so our readline can stop
        if isinstance(handle, multiprocessing.connection.Connection):
            handle.stop_event = stop_event

        log.info('Starting reader process')
        log.info('Queue type: %s', type(queue))
        if handle.closed:
            log.warning('Pipe handle is already closed')

        else:
            # Flush out any potentially waiting content
            handle.flush()

            # https://stackoverflow.com/a/2813530
            while True:
                try:
                    line = handle.readline()
                except (ValueError, EOFError):
                    log.info('Unexpected EOF')
                    break

                # Empty line should signify end of file
                if line is None or line == '' or len(line) == 0:
                    break

                # Wrap in a ContentWrapper
                content = conditional_wrap(line, wrap_when=wrap_when, wrap_threshold=wrap_threshold)

                log.info('Read line, trying to get a lock')
                with queue_lock:
                    log.info('Enqueing line of character length %s, byte length %s',
                             len(content), get_len(content))
                    if isinstance(content, ContentWrapper):  # Wrapped Connections return a CW
                        log.debug('Content is in a ContentWrapper')

                    try:
                        queue.put(content)
                        log.debug('Sent to queue')
                    except EOFError:
                        log.info('Unexpected destination queue EOF')
                        break

                    # Increment counter
                    messages_processed.increment()

                # Check whether we should stop now
                if stop_event.is_set():
                    log.info('Reader asked to stop')
                    break

            # Close the handle if we opened it
            if handle_name:
                handle.close()

            # Clean up references
            # Prevent "UserWarning: ResourceTracker called reentrantly for resource cleanup,
            # which is unsupported. The semaphore object '/<name>' might leak."
            queue_lock = None
            stop_event = None
            messages_processed = None
            handle.stop_event = None
            handle = None

        log.info('Reader sub-process complete')
