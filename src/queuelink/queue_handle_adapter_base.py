# -*- coding: utf-8 -*-
"""Parent class for QueueHandleAdapterReader and QueuePipeAdapterWriter"""
from __future__ import unicode_literals

import io
import random
import tempfile  # For comparisons
import threading

from pickle import PicklingError  # nosec
from threading import Thread  # For non-multi-processing queues
from typing import Union

# Multiprocessing imports
import multiprocessing

from _io import _IOBase  # For comparisons

from .classtemplate import ClassTemplate
from .exceptionhandler import HandleAlreadySet
from .common import DIRECTION
from .common import is_threaded
from .common import UNION_SUPPORTED_EVENTS, UNION_SUPPORTED_LOCKS, UNION_SUPPORTED_QUEUES


class MessageCounter(object):
    """Track the number of messages processed by an Adapter.

    Access the count with MessageCenter.value"""
    def __init__(self, thread_only: bool=False):
        self.counter = threading.local() if thread_only else multiprocessing.Value('Q')
        self.counter.value = 0

    def increment(self) -> None:
        """Increment the message counter."""
        self.counter.value += 1

    def __getattr__(self, attr):
        if attr == 'value':
            return object.__getattribute__(self, 'counter').value

        return object.__getattribute__(self, attr)


class _QueueHandleAdapterBase(ClassTemplate):
    """QueueHandleAdapter abstract implementation"""
    def __init__(self,
                 queue: UNION_SUPPORTED_QUEUES,
                 *,  # End of positional arguments
                 subclass_name: str,
                 queue_direction: DIRECTION,
                 name: str=None,
                 handle: io.IOBase=None,
                 log_name: str=None,
                 start_method: str=None,
                 thread_only: bool=False,
                 **kwargs):
        """
        Args:
            queue: The queue to attach
            subclass_name: Name of the concrete class implementation
            queue_direction: Indicate direction relative to pipe;
                e.g. from stdout, the flow is (PIPE => QUEUE)
                => CLIENT QUEUES (from pipe/queue into client queues), and
                therefore queue_direction would be "source".
            name: Name to use in logging for this instance
            handle: The IO handle
            log_name: Additional name to use in logging for this instance
            start_method: Name of the multiprocessing start method to use (fork, forkserver, spawn)
            thread_only: True to keep processing in a single thread using threading
        """
        # Unique ID for this PrPipe
        # Not used for cryptographic purposes, so excluding from Bandit
        self.id = \
            ''.join([random.choice(  # nosec
                '0123456789ABCDEF') for x in range(6)])

        # Name for this instance, typically stdin/stdout/stderr
        self.name = name

        # Name of the subclass (QueueHandleAdapterReader, QueuePipeAdapterWriter)
        self.subclass_name = subclass_name

        # Additional naming for differentiating multiple instances
        self.log_name = log_name

        # Initialize the logger
        self._initialize_logging_with_log_name(self.subclass_name)

        # Which "direction" client queues will use in the queue_link
        self.queue_direction = queue_direction
        self.client_direction = DIRECTION.FROM if queue_direction == DIRECTION.TO \
            else DIRECTION.TO

        # Whether to use only threading (vs multiprocessing)
        self.thread_only = thread_only

        # Which multiprocess context to use
        self.multiprocessing_ctx = multiprocessing.get_context(start_method)

        # Whether we have ever been started
        self.started = self.multiprocessing_ctx.Event()

        # Whether we have been asked to stop
        self.stopped = self.multiprocessing_ctx.Event()

        # Whether the queue adapter process should stop
        self.stop_event = self.multiprocessing_ctx.Event()

        # The queue proxy to be used as the main input or output buffer.
        # Attaching this to the queue link is the responsibility of subclasses.
        self.queue = queue

        # Lock to notify readers/writers that a read/write is in progress
        self.queue_lock = self.multiprocessing_ctx.Lock()

        # Store the number of messages processed
        # Q unsigned long long https://docs.python.org/3/library/array.html#module-array
        self.messages_processed = MessageCounter()

        # Store other args
        self.kwargs = kwargs

        self.process = None
        self.handle = None
        if handle is not None:
            self.set_handle(handle)

    # Class contains Locks and Queues which cannot be pickled
    def __getstate__(self):
        """Prevent _QueueHandleAdapterBase from being pickled across Processes

        Raises:
            Exception
        """
        raise PicklingError("Don't pickle me!")

    def set_handle(self, handle: Union[io.IOBase, str]) -> None:
        """Set the handle to read from or write to.

        Args:
            handle: An open handle (subclasses of file, IO.IOBase)

        Raises:
            HandleAlreadySet
        """
        if self.process is not None:
            raise HandleAlreadySet

        # Store the pipehandle
        self.handle = handle

        # Process name
        process_name = f'{self.subclass_name}-{self.name}'

        if self.log_name is not None:
            process_name = f'{process_name}-{self.log_name}'

        # If the handle is a BufferedReader we have to stay in the same process
        if isinstance(handle, (_IOBase, tempfile._TemporaryFileWrapper)) and not self.thread_only:
            self._log.warning('Adapter process %s will only be threaded as we cannot '
                              'send an open handle to another process.', process_name)
            self.thread_only = True

        # Select the right concurrency mechanism
        threaded = is_threaded(self.queue)
        Parallel = Thread if threaded or self.thread_only else self.multiprocessing_ctx.Process

        # Arguments for
        arg_dict = {
            "name": self.name,
            "handle": handle,
            "queue": self.queue,
            "queue_lock": self.queue_lock,
            "stop_event": self.stop_event,
            "messages_processed": self.messages_processed}
        arg_dict.update(self.kwargs)

        self._log.debug("Setting %s adapter process for %s pipe handle",
                        self.subclass_name, self.name)
        self.process = Parallel(target=self.queue_handle_adapter,
                                name=process_name,
                                kwargs=arg_dict)
        self.process.daemon = True
        self.process.start()
        self.started.set()
        self._log.debug("Kicked off %s adapter process for %s pipe handle",
                        self.subclass_name, self.name)

    def __del__(self):
        self.close()

    @staticmethod
    def queue_handle_adapter(*,  # All named parameters are required keyword arguments
                             name: str,
                             handle: io.IOBase,
                             queue: UNION_SUPPORTED_QUEUES,
                             queue_lock: UNION_SUPPORTED_LOCKS,
                             stop_event: UNION_SUPPORTED_EVENTS,
                             messages_processed: MessageCounter,
                             trusted: bool,
                             **kwargs) -> None:
        """Override me in a subclass to do something useful"""

    def _stop(self) -> None:
        """Internal stop method"""
        # Mark that we have been asked to stop
        self.stopped.set()

        # Stop the adapter
        self.stop_event.set()

        while True:
            self.process.join(timeout=1)

            if self.process.is_alive():
                pass
            else:
                break

    def close(self) -> None:
        """Stop the adapter and queue link and clean up.

        Does not force a drain of the queues.
        """
        if hasattr(self, '_stop') and hasattr(self, 'started'):
            if self.started:
                self._stop()

        # Delete/unlink other resources
        attributes = [
            'started',
            'stopped',
            'stop_event',
            'queue_lock',
            'queue',
            'handle',
            'messages_processed']

        for attr in attributes:
            if hasattr(self, attr):
                setattr(self, attr, None)

    def is_alive(self) -> bool:
        """Check whether the thread/process managing the movement is still active

        Returns:
            True if the adapter thread/process is still running, False otherwise.
        """
        return self.process.is_alive()

    def is_drained(self) -> bool:
        """Check alive and empty

        Attempts clean semantic response to "is there, or will there be, data
        to read?"

        Returns:
            True if fully drained, False if not
        """
        drained = True

        # If we aren't started, we have to stop here. The process isn't ready
        # to call is_alive()
        if not self.started.is_set():
            return False

        # Alive (True) means we are not drained
        drained = drained and not self.is_alive()

        return drained

    def get_messages_processed(self) -> int:
        """Return the number of messages moved by this adapter

        Returns:
            The number of messages processed by this adapter.
        """
        return self.messages_processed.value
