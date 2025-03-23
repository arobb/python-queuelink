# -*- coding: utf-8 -*-
"""Manages the pull/push with queues"""
from __future__ import unicode_literals

from typing import List, Union

import functools
import logging

from builtins import str as text
from inspect import signature
from queue import Empty
from threading import Thread  # For non-multi-processing queues

# Multiprocessing imports
import multiprocessing

# Internal imports
from .classtemplate import ClassTemplate
from .exceptionhandler import ProcessNotStarted
from .metrics import Metrics
from .common import DIRECTION
from .common import PRIORITY_QUEUES, SIMPLE_QUEUES, UNION_SUPPORTED_QUEUES
from .common import new_id, is_threaded, safe_get


def validate_direction(func):
    """Decorator to check that 'direction' is an acceptable value.

    One of DIRECTION.FROM or DIRECTION.TO.

    :raises TypeError
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):

        # Extract the function signature so we can check for direction
        sig = signature(func)
        bound = sig.bind_partial(*args, **kwargs)

        # Validate direction if present
        if "direction" in bound.arguments:
            arg_direction = bound.arguments['direction']

            # If the direction is valid, just keep going
            if arg_direction in DIRECTION:
                pass

            # If the direction is invalid, throw an error
            else:
                raise TypeError(
                    "destination must be a value from DIRECTION")

        # Call the normal function
        return func(*args, **kwargs)

    return wrapper


class LimitedLengthQueue(object):
    """Wrapper for an existing Queue to keep the length limited.

    NOT thread/process safe, only intended to be used by a single producer (i.e., Publishers).
    """
    def __init__(self,
                 queue_instance: multiprocessing.queues.Queue,
                 max_size: int=0):
        self._queue = queue_instance
        self.max_size = max_size
        self._queue_length = 0

        if not self._queue.empty():
            raise ValueError('Cannot start with a non-empty Queue!')

    def put(self, *args, **kwargs):
        """Add an element to the queue"""
        while self._queue_length >= self.max_size:
            self.get()

        self._queue.put(*args, **kwargs)
        self._queue_length += 1

    def get(self, *args, **kwargs):
        """Retrieve an element from the queue

        :throws Empty
        """
        value = self._queue.get(*args, **kwargs)
        self._queue_length -= 1

        return value

    def qsize(self):
        """Returns the number of elements in the queue

        Based on the wrapper's counter; does not rely on the underlying queue implementation.
        """
        return self._queue_length

    def __getattr__(self, item):
        if item in ('_queue', '_queue_length', 'max_size', 'get', 'put'):
            return self.__getattribute__(item)

        return getattr(self._queue, item)


class QueueLink(ClassTemplate):
    """Manages publishing from source and client queues"""

    def __init__(self,
                 source: UNION_SUPPORTED_QUEUES=None,
                 destination: Union[UNION_SUPPORTED_QUEUES, List[UNION_SUPPORTED_QUEUES]]=None,
                 name: str=None,
                 log_name: str=None,
                 start_method: str=None,
                 thread_only: bool=False,
                 link_timeout: float=0.01):
        """Manages the pull/push with queues

        :param UNION_SUPPORTED_QUEUES source: Queue to act as the source
        :param UNION_SUPPORTED_QUEUES destination: Queue or list of queues to act as a destination
        :param str name: Appended to class name in log records (``cl.name``)
        :param str log_name: Appended to class name.name (``cl.name.log_name``)
            or just class name if ``name`` is not provided
        :param str start_method: For multi-process use: fork, spawn or forkserver
        :param bool thread_only: Only use threads, not separate processes, for links
        :param float link_timeout: Tune the queue.get(timeout=link_timeout) value; default 0.01 sec
        """
        # Unique ID
        # Not used for cryptographic purposes, so excluding from Bandit
        self.id = new_id()

        self.name = name
        self.log_name = log_name

        self._initialize_logging_with_log_name(__name__)

        # Timeout for publisher queue.get calls
        self.link_timeout = link_timeout

        # Thread only usage (no multiprocessing)
        self.thread_only = thread_only

        # Start method for process-based use
        self.start_method = start_method

        # Use the correct types when creating multithreaded/process Events
        self.multiprocess_ctx = multiprocessing.get_context(self.start_method)

        # Indicate whether we have ever been started (Event())
        self.started = self.Event()

        # List of locks allows decoupled IO while also preventing the set of
        # queues from changing during IO operations
        self.queues_lock = self.Lock()
        self.last_queue_id = 0
        self.client_queues_source = {}
        self.client_queues_destination = {}
        self.client_pair_publishers = {}
        self.publisher_stops = {}

        # Metrics
        self.metrics_queue = self.multiprocess_ctx.Queue()

        # Short-circut usage
        if source:
            self.register_queue(queue_proxy=source, direction=DIRECTION.FROM)

        if destination:
            if not isinstance(destination, list):
                destination = [destination]

            for q_inst in destination:
                self.register_queue(queue_proxy=q_inst, direction=DIRECTION.TO)


    # Class contains Locks and Queues which cannot be pickled
    def __getstate__(self):
        """Prevent _QueueHandleAdapterBase from being pickled across Processes

        Raises:
            Exception
        """
        raise TypeError("Don't pickle me!")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()

    def close(self):
        """Remove managed objects started within QueueLink"""

        # Make sure processes are stopped
        if hasattr(self, 'stop') and hasattr(self, 'started'):
            if self.started:
                self.stop()

        # Unset these variables to release any objects they held
        unset_list = ['metrics_queue',  # Metrics
                      'started',  # Started event
                      'queues_lock',  # Queues lock
                      'publisher_stops',  # Publisher stop events
                      'client_queues_source',  # Queue references
                      'client_queues_destination',  # Queue references
                      'client_pair_publishers']  # Queue references

        for var in unset_list:
            if hasattr(self, var):
                setattr(self, var, None)

    def _initialize_logging_with_log_name(self, class_name: str):
        """Need to reverse the print order of log_name and name"""
        if hasattr(self, '_log'):
            if self._log is not None:
                return

        # Make a helpful name
        if self.name is None:
            name = class_name
        else:
            name = f'{class_name}.{self.name}'

        if self.log_name is not None:
            name = f'{name}.{self.log_name}'

        self._log = logging.getLogger(name)
        self.add_logging_handler(logging.NullHandler())

    def Event(self, *args, **kwargs):  # pylint: disable=invalid-name
        """Create a context-appropriate Event"""
        return self.multiprocess_ctx.Event(*args, **kwargs)

    def Lock(self, *args, **kwargs):  # pylint: disable=invalid-name
        """Create a context-appropriate Lock"""
        return self.multiprocess_ctx.Lock(*args, **kwargs)

    def Process(self, *args, **kwargs):  # pylint: disable=invalid-name
        """Create a context-appropriate Process"""
        return self.multiprocess_ctx.Process(*args, **kwargs)

    def Queue(self, *args, **kwargs):  # pylint: disable=invalid-name
        """Create a context-appropriate Queue"""
        return self.multiprocess_ctx.Queue(*args, **kwargs)

    def stop(self):
        """Use to stop somewhat gracefully"""
        self._stop_publishers()

    @staticmethod
    def _publisher(stop_event,
                   source_id,
                   source_queue,
                   dest_queues_dict,
                   timeout,
                   metrics_queue: UNION_SUPPORTED_QUEUES,
                   metric_interval: int=100,
                   name=None):
        """Move messages from the source queue to the destination queue

        :param timeout=0.1; 100ms responsive-ish to shutdown and minimizes thrashing
        """
        # Make a helpful logger name
        if name is None:
            logger_name = f'{__name__}.publisher.{source_id}'
        else:
            logger_name = f'{__name__}.publisher.{name}.{source_id}'

        log = logging.getLogger(logger_name)
        log.addHandler(logging.NullHandler())

        # Set up metrics
        counter = 0
        metrics = Metrics()

        latency_metric_id = metrics.add_element(metric_type='timing', name='pipe latency')
        metrics.start(latency_metric_id)
        metrics_queue_limited = LimitedLengthQueue(queue_instance=metrics_queue, max_size=100)

        counting_metric_id = metrics.add_element(metric_type='counting', name='movement count')

        while True:
            # Check for stop
            if stop_event.is_set():
                log.info("Stopping due to stop event")
                metrics_queue_limited.put(metrics.get_all_data())
                return

            try:
                log.debug("Trying to get line from source in pair %s",
                          source_id)
                line = safe_get(source_queue, timeout=timeout, stop_event=stop_event)

                # Distribute the line to all downstream queues
                for dest_id, dest_queue in dest_queues_dict.items():
                    log.info("Writing line from source %s to dest %s",
                             source_id, dest_id)
                    dest_queue.put(line)

                # Mark that we've finished processing the item from the queue
                if hasattr(source_queue, 'task_done'):
                    source_queue.task_done()

                # Mark latency
                counter += 1
                metrics.lap(latency_metric_id)
                metrics.increment(counting_metric_id)

                # Send metric info
                if counter % metric_interval == 0:
                    metrics_queue_limited.put(metrics.get_all_data())

            except Empty:
                log.debug("No lines to get from source in pair %s", source_id)
                continue

            except EOFError:
                log.debug("Source in pair %s no longer available", source_id)

            except BrokenPipeError:
                log.debug("One pipe in pair %s is no longer available",
                          name if name else source_id)
                return

    def get_queue(self, queue_id: Union[str, int]):
        """Retrieve a client's Queue proxy object

        Args:
            queue_id (string): ID of the client

        Returns:
            QueueProxy
        """
        if queue_id in self.client_queues_source:
            queue_list = self.client_queues_source
        else:
            queue_list = self.client_queues_destination

        return queue_list[text(queue_id)]

    @validate_direction
    def register_queue(self, queue_proxy, direction: DIRECTION) -> str:
        """Register a multiprocessing.JoinableQueue to this link

        For a new "source" queue, a publishing process will be created to send
        all additions down to destination queues.

        For a new "destination" queue, all new additions to "source" queues
        will be added to this queue.

        Returns the numeric ID for the new client, which must be used in all
        future interactions.

        Args:
            queue_proxy (QueueProxy): Proxy object to a JoinableQueue
            direction (DIRECTION): FROM or TO

        Returns:
            string. The client's ID for access to this queue

        """
        # Calculate the opposite direction
        op_direction = DIRECTION.TO if direction == DIRECTION.FROM else DIRECTION.FROM

        # Warnings
        # Priority Queues
        if isinstance(queue_proxy, tuple(PRIORITY_QUEUES)):
            self._log.warning('Entries in a PriorityQueue must have the correct format (tuple or '
                           'simple class with a priority value) or the queue will block.')

        # SimpleQueues
        if direction == DIRECTION.FROM and isinstance(queue_proxy, tuple(SIMPLE_QUEUES)):
            self._log.warning('Using multiple readers on a SimpleQueue that is a source for a '
                              'QueueLink instance (including other QueueLink instances) can cause '
                              'a deadlock. Queue type: %s.', type(queue_proxy))

        with self.queues_lock:
            # Get the queue list and opposite queue list
            queue_dict = getattr(self, f'client_queues_{direction}')
            op_queue_dict = getattr(self, f'client_queues_{op_direction}')

            # Make sure we don't accidentally create a loop, or add multiple
            # times
            if queue_proxy in queue_dict.values():
                raise ValueError("Cannot add this queue again")

            if queue_proxy in op_queue_dict.values():
                raise ValueError('This queue is in the opposite list. Cannot'
                                 f' add to the {direction} list because it would cause'
                                 ' a circular reference.')

            # Increment the current queue_id
            queue_id = self.last_queue_id + 1
            self.last_queue_id = queue_id

            # Store the queue proxy in the appropriate queue list
            queue_dict[text(queue_id)] = queue_proxy

            # (Re)create the publishing processes
            # New source:
            #   Just add a new publishing process and send it the list of
            #   destinations.
            if direction == DIRECTION.FROM:
                self._log.debug("Registering source client")
                source_id = queue_id

                # Create and store a new stop event
                stop_event = self.Event()
                self.publisher_stops[text(source_id)] = stop_event

                # Start the publisher
                # This doesn't do anything unless there are some available
                # destinations
                self._start_publisher(source_id)

            # New destination:
            #   Stop all existing publishing processes and restart with updated
            #   destination queue list.
            else:
                self._log.debug("Registering destination client")

                # Stop current processes
                self._stop_publishers()

                # Restart publishers with the updated destinations
                for source_id in self.client_queues_source:
                    self._log.debug("Starting publisher %s", source_id)
                    self._start_publisher(source_id)

        return text(queue_id)

    def read(self, queue_proxy: UNION_SUPPORTED_QUEUES) -> str:
        """Register a source queue

        Args:
            queue_proxy (QueueProxy): Queue or proxy object to a queue

        Returns:
            string. The client's ID for access to this queue
        """
        return self.register_queue(queue_proxy=queue_proxy, direction=DIRECTION.FROM)

    def write(self, queue_proxy: UNION_SUPPORTED_QUEUES) -> str:
        """Register a destination queue

        Args:
            queue_proxy (QueueProxy): Queue or proxy object to a queue

        Returns:
            string. The client's ID for access to this queue
        """
        return self.register_queue(queue_proxy=queue_proxy, direction=DIRECTION.TO)

    def _start_publisher(self, source_id: str):
        """Eliminate duplicated Process() call in register_queue

        Start a publisher process to move items from the source queue to
        the destination queues

        Should only be called by register_queue and unregisterQueue (they hold
        a lock for the queue dictionaries while this runs.)
        """
        stop_event = self.publisher_stops[text(source_id)]
        source_queue = self.client_queues_source[text(source_id)]
        dest_queues_dict = self.client_queues_destination
        destination_names = "-".join(dest_queues_dict.keys())

        # Make sure we don't ovewrite a running Process
        try:
            if self.client_pair_publishers[text(source_id)].exitcode is None:
                raise ValueError("Cannot overwrite a running Process!")

        # If this is new, there won't be an existing value here
        except KeyError:
            pass

        # Make sure there is at least one desination queue
        if len(dest_queues_dict) == 0:
            return

        # Start a publisher process to move items from the source
        # queue to the destination queues
        self._log.info("Starting queue link for source %s to %s",
                       source_id, destination_names)

        # Name the process
        if self.log_name is not None:
            process_name = f'ClientPublisher-{self.log_name}-{source_id}'
        else:
            process_name = f'ClientPublisher-{source_id}'

        # Determine whether to use a thread or process based publisher
        threaded = is_threaded([source_queue, *dest_queues_dict.values()])

        # Decide whether to use a local thread or process-based publisher
        Parallel = Thread if threaded or self.thread_only else self.Process

        # Start the publisher
        proc = Parallel(target=self._publisher,
                        name=process_name,
                        kwargs={"name": self.name,
                               "stop_event": stop_event,
                               "source_id": source_id,
                               "source_queue": source_queue,
                               "dest_queues_dict": dest_queues_dict,
                               "timeout": self.link_timeout,
                               "metrics_queue": self.metrics_queue})
        proc.daemon = True
        proc.start()
        self.started.set()
        self.client_pair_publishers[text(source_id)] = proc

    def _stop_publisher(self, source_id: str):
        """Stop a current publisher process"""
        self._log.debug("Stopping publisher %s", source_id)
        stop_event = self.publisher_stops[text(source_id)]
        stop_event.set()

        # Wait for the process to stop
        try:
            proc_old = self.client_pair_publishers[text(source_id)]

            while True:
                proc_old.join(timeout=1)

                if proc_old.is_alive():
                    self._log.info("Waiting for client %s to stop", source_id)
                else:
                    break

        # If no current publishers are running, a KeyError will be raised
        except KeyError:
            pass

        # Flip the "stop" event back to normal
        stop_event.clear()

    def _stop_publishers(self):
        """Stop current publisher processes"""
        self._log.debug("Stopping any current publishers")
        for source_id in self.client_queues_source:
            self._stop_publisher(source_id)

    @validate_direction
    def unregister_queue(self, queue_id: Union[str, int], direction: DIRECTION):
        """Detach a Queue proxy from this _QueueHandleAdapterBase

        Returns the clientId that was removed

        Args:
            queue_id (string): ID of the client
            direction (DIRECTION): source or destination

        Returns:
            string. ID of the client queue

        """
        with self.queues_lock:
            queue_list = getattr(self, f'client_queues_{direction}')
            if text(queue_id) in queue_list:
                queue_list.pop(queue_id)

            if direction == DIRECTION.FROM:
                source_id = queue_id

                # Stop the source publisher
                # Wait for the process to stop
                self._stop_publisher(source_id)

                # Remove the stop
                self.publisher_stops.pop(queue_id)

            else:
                # Stop current processes
                self._stop_publishers()

                # Restart publishers with the updated destinations
                for source_id in self.client_queues_source:
                    self._start_publisher(source_id)

        return text(queue_id)

    def is_empty(self, queue_id:str =None):
        """Checks whether the primary Queue or any clients' Queues are empty

        Returns True ONLY if ALL queues are empty if queue_id is None
        Returns True ONLY if both main queue and specified client queue are
            empty when queue_id is provided

        Args:
            queue_id (string): ID of the client

        Returns:
            bool
        """
        with self.queues_lock:
            if queue_id is not None:
                self._log.debug("Checking if %s is empty", queue_id)
                empty = True

                # If this is a downstream queue, we need to make sure all
                # upstream queues are empty, too
                if queue_id in self.client_queues_destination:
                    self._log.debug("First checking upstream queue(s) of %s", queue_id)

                    for source_id in self.client_queues_source:
                        source_empty = self.get_queue(source_id).empty()
                        self._log.info("Source %s is empty: %s",
                                       source_id, source_empty)
                        empty = empty and source_empty

                queue_empty = self.get_queue(queue_id).empty()
                empty = empty and queue_empty
                self._log.info("%s is empty: %s", queue_id, queue_empty)

            else:
                empty = True

                for client_queue in list(self.client_queues_source.values()):
                    empty = empty and client_queue.empty()

                for client_queue in list(self.client_queues_destination.values()):
                    empty = empty and client_queue.empty()

            self._log.debug("Reporting queue link empty: %s", empty)
            return empty

    def is_alive(self):
        """Whether all of the publishers are alive

        :raises ProcessNotStarted if we've never started
        :returns bool
        """
        alive = True

        if not self.started.is_set():
            raise ProcessNotStarted(f'{self.name} has not started')

        for proc in self.client_pair_publishers.values():
            alive = alive and proc.is_alive()

        return alive

    def is_drained(self, queue_id: str=None):
        """Check alive and empty

        Attempts clean semantic response to "is there, or will there be, data
        to read?"

        :returns bool
        """
        drained = True

        # Don't want to check "alive", as these processes run until a parent
        # processes stops them (or is stopped).
        # If we haven't started yet, we are not drained
        if not self.started.is_set():
            return False

        drained = drained and self.is_empty(queue_id=queue_id)

        return drained

    @validate_direction
    def destructive_audit(self, direction: DIRECTION):
        """Print a line from each client Queue from the provided direction

        Args:
            direction (DIRECTION): source or destination

        This is a destructive operation, as it *removes* a line from each Queue

        :raises Empty
        """
        with self.queues_lock:
            queue_list = getattr(self, f'client_queues_{direction}')

            for q_id in list(queue_list):
                try:
                    target_queue = self.get_queue(q_id)
                    self._log.info("queue_id %s: %s",
                                   text(q_id), safe_get(target_queue, block=False))
                except Empty:
                    self._log.info("queue_id %s is empty", text(q_id))

    def get_metrics(self) -> dict:
        """Retrieve metrics about the link

        :returns dict
        """
        value = {}

        try:
            while True:
                value = self.metrics_queue.get_nowait()

        except Empty:
            pass

        return value
