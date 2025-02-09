# -*- coding: utf-8 -*-
"""Parent class for QueueHandleAdapterReader and QueuePipeAdapterWriter"""
from __future__ import unicode_literals

import random
import sys

import multiprocessing

from threading import Thread  # For non-multi-processing queues

from .classtemplate import ClassTemplate
from .exceptionhandler import HandleAlreadySet
from .contentwrapper import WRAP_WHEN
from .common import UNION_SUPPORTED_QUEUES
from .common import is_threaded


class _QueueHandleAdapterBase(ClassTemplate):
    def __init__(self,
                 queue,
                 subclass_name: str,
                 queue_direction: str,
                 name:str =None,
                 handle=None,
                 log_name:str =None,
                 start_method: str=None,
                 thread_only: bool=False,
                 trusted: bool=False,
                 wrap_when: WRAP_WHEN=WRAP_WHEN.NEVER):
        """QueuePipeAdapter abstract implementation

        Args:
             queue_direction (string): Indicate direction relative to pipe;
                e.g. for PrPipeReader from stdout, the flow is (PIPE => QUEUE)
                => CLIENT QUEUES (from pipe/queue into client queues), and
                therefore queue_direction would be "source".
             trusted: Whether to trust Connection objects; True uses .send/.recv,
                False send_bytes/recv_bytes
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
        self.client_direction = "source" if queue_direction == "destination" \
            else "destination"

        # Whether to use only threading (vs multiprocessing)
        self.thread_only = thread_only

        # Whether to trust Connection objects; True uses .send/.recv, False send_bytes/recv_bytes
        self.trusted = trusted

        # When to use a ContentWrapper
        self.wrap_when = wrap_when

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
        raise Exception("Don't pickle me!")

    def set_handle(self, handle):
        """Set the pipe handle to use

        Args:
            handle (io.IOBase): An open handle (subclasses of file,
                IO.IOBase)

        Raises:
            HandleAlreadySet
        """
        if self.process is not None:
            raise HandleAlreadySet

        # Store the pipehandle
        self.handle = handle

        # Process name
        process_name = "{}-{}".format(self.subclass_name, self.name)

        if self.log_name is not None:
            process_name = "{}-{}".format(process_name, self.log_name)

        # Select the right concurrency mechanism
        threaded = is_threaded(self.queue)
        Parallel = Thread if threaded or self.thread_only else self.multiprocessing_ctx.Process

        self._log.debug("Setting %s adapter process for %s pipe handle",
                        self.subclass_name, self.name)
        self.process = Parallel(target=self.queue_handle_adapter,
                                name=process_name,
                                kwargs={"name": self.name,
                                        "handle": handle,
                                        "queue": self.queue,
                                        "queue_lock": self.queue_lock,
                                        "stop_event": self.stop_event,
                                        "trusted": self.trusted,
                                        "wrap_when": self.wrap_when})
        self.process.daemon = True
        self.process.start()
        self.started.set()
        self._log.debug("Kicked off %s adapter process for %s pipe handle",
                        self.subclass_name, self.name)

    def __del__(self):
        self.close()

    @staticmethod
    def queue_handle_adapter(name,
                             handle,
                             queue,
                             queue_lock,
                             stop_event):
        """Override me in a subclass to do something useful"""

    def get_queue(self, client_id):
        """Retrieve a client's Queue proxy object

        Args:
            client_id (string): ID of the client

        Returns:
            multiprocessing.JoinableQueue:
        """
        return self.queue_link.get_queue(client_id)

    def _stop(self):
        """Internal stop method"""
        # Mark that we have been asked to stop
        self.stopped.set()

        # Stop the adapter
        self.stop_event.set()

        while True:
            self.process.join(timeout=1)

            if self.process.is_alive():
                self._log.info("Waiting for adapter to stop")
            else:
                break

    def close(self):
        """Stop the adapter and queue link and clean up.

        Does not force a drain of the queues.
        """
        if self._stop and self.started:
            self._stop()

        # Delete/unlink other resources
        self.started = None
        self.stopped = None
        self.stop_event = None
        self.queue_lock = None
        self.queue = None
        self.handle = None

    def is_empty(self, client_id=None):
        """Checks whether the primary Queue or any clients' Queues are empty

        Returns True ONLY if ALL queues are empty if clientId is None
        Returns True ONLY if both main queue and specified client queue are
            empty when clientId is provided

        Args:
            client_id (string): ID of the client

        Returns:
            bool
        """
        with self.queue_lock:
            if client_id is not None:
                empty = self.queue.empty() \
                        and self.queue_link.is_empty(client_id)

                self._log.debug("Reporting pipe empty for client %s: %s",
                                client_id, empty)

            else:
                empty = self.queue.empty() \
                        and self.queue_link.is_empty()

                self._log.debug("Reporting pipe empty: %s", empty)

            return empty

    def is_alive(self):
        """Check whether the thread managing the pipe > Queue movement
        is still active

        Returns:
            bool
        """
        return self.process.is_alive()

    def is_drained(self, client_id=None):
        """Check alive and empty

        Attempts clean semantic response to "is there, or will there be, data
        to read?"

        Args:
            client_id (string): Registration ID to check

        Returns:
            bool: True if fully drained, False if not
        """
        drained = True

        # If we aren't started, we have to stop here. The process isn't ready
        # to call is_alive()
        if not self.started.is_set():
            return False

        # Alive (True) means we are not drained
        drained = drained and not self.is_alive()

        # Checks a similar function on the queue_link
        # drained = drained and self.queue_link.is_drained(queue_id=client_id)

        # Not checking self.is_empty because that is effectively done by
        # running self.queue_link.is_drained()

        return drained
