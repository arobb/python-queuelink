# -*- coding: utf-8 -*-
"""Manages the pull/push with queues"""
from __future__ import unicode_literals
from __future__ import annotations

from typing import List, Tuple, Union

import functools
import logging
import multiprocessing
import queue
import random
import sys

import queue as queue_module
import time

from builtins import dict
from builtins import str as text
from inspect import signature
from multiprocessing import Event
from multiprocessing import Lock
from multiprocessing import Process
from multiprocessing import queues as mp_queue_classes
from multiprocessing.managers import BaseProxy
from queue import Empty
from threading import Thread  # For non-multi-processing queues

from .classtemplate import ClassTemplate
from .exceptionhandler import ProcessNotStarted
from .timer import Timer


# List of queue types that are threaded (vs multiprocessing)
THREADED_QUEUES = [
    queue_module.Queue,
    queue_module.LifoQueue,
    queue_module.PriorityQueue,
    queue_module.SimpleQueue
]

# List of PriorityQueue types
PRIORITY_QUEUES = [
    queue_module.PriorityQueue
]

# List of SimpleQueue types
SIMPLE_QUEUES = [
    queue_module.SimpleQueue,
    mp_queue_classes.SimpleQueue
]

# Union type for typing support
UNION_SUPPORTED_QUEUES = Union[queue.Queue,
                               queue.LifoQueue,
                               queue.PriorityQueue,
                               queue.SimpleQueue,
                               multiprocessing.queues.Queue,
                               multiprocessing.queues.JoinableQueue,
                               multiprocessing.queues.SimpleQueue,
                               BaseProxy]


def is_threaded(queue_list: List):
    """Check whether one or more queues are threaded

    :param queue: Any queue or list of queues (any type)
    :return bool
    """
    if not isinstance(queue_list, list):
        queue_list = [queue_list]

    for q in queue_list:
        if isinstance(q, tuple(THREADED_QUEUES)):
            return True

    return False


def validate_direction(func):
    """Decorator to check that 'direction' is an acceptable value.

    One of 'source' or 'destination'.

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
            if arg_direction in ("source", "destination"):
                pass

            # If the direction is invalid, throw an error
            else:
                raise TypeError(
                    "destination must be 'source' or 'destination'")

        # Call the normal function
        return func(*args, **kwargs)

    return wrapper


class QueueLink(ClassTemplate):
    """Manages publishing from source and client queues"""

    def __init__(self,
                 source: UNION_SUPPORTED_QUEUES=None,
                 destination: Union[UNION_SUPPORTED_QUEUES, List[UNION_SUPPORTED_QUEUES]]=None,
                 name: str=None,
                 log_name: str=None,
                 start_method: str=None,
                 thread_only: bool=False,
                 link_timeout: float=0.1) -> Union[None, Tuple[str, Union[None, str, List[str]]]]:
        """Manages the pull/push with queues

        :param UNION_SUPPORTED_QUEUES source: Queue to act as the source
        :param UNION_SUPPORTED_QUEUES destination: Queue or list of queues to act as a destination
        :param str name: Appended to class name in log records (``cl.name``)
        :param str log_name: Appended to class name.name (``cl.name.log_name``)
            or just class name if ``name`` is not provided
        :param str start_method: For multi-process use: fork, spawn or forkserver
        :param bool thread_only: Only use threads, not separate processes, for links
        :param float link_timeout: Tune the queue.get(timeout=link_timeout) value; default 0.1 sec
        """
        # Unique ID
        # Not used for cryptographic purposes, so excluding from Bandit
        self.id = \
            ''.join([random.choice(  # nosec
                '0123456789ABCDEF') for x in range(6)])

        self.name = name
        self.log_name = log_name

        self._initialize_logging_with_log_name(__name__)

        # Timeout for publisher queue.get calls
        self.link_timeout = link_timeout

        # Indicate whether we have ever been started
        self.started = Event()

        # Indicate whether we have been asked to stop
        self.stopped = Event()

        # List of locks allows decoupled IO while also preventing the set of
        # queues from changing during IO operations
        self.queues_lock = Lock()
        self.last_queue_id = 0
        self.client_queues_source = dict()
        self.client_queues_destination = dict()
        self.client_pair_publishers = dict()
        self.publisher_stops = dict()

        # Start method for process-based use
        self.start_method = start_method

        # Thread only usage (no multiprocessing)
        self.thread_only = thread_only

        # Short-circut usage
        if source:
            self.register_queue(queue_proxy=source, direction='source')

        if destination:
            if not isinstance(destination, list):
                destination = [destination]

            for d in destination:
                self.register_queue(queue_proxy=d, direction='destination')


    # Class contains Locks and Queues which cannot be pickled
    def __getstate__(self):
        """Prevent _QueuePipeAdapterBase from being pickled across Processes

        Raises:
            Exception
        """
        raise Exception("Don't pickle me!")

    def _initialize_logging_with_log_name(self, class_name: str):
        """Need to reverse the print order of log_name and name"""
        if hasattr(self, '_log'):
            if self._log is not None:
                return

        # Make a helpful name
        if self.name is None:
            name = class_name
        else:
            name = "{}.{}".format(class_name, self.name)

        if self.log_name is not None:
            name = "{}.{}".format(name, self.log_name)

        self._log = logging.getLogger(name)
        self.add_logging_handler(logging.NullHandler())

    def stop(self):
        """Use to stop somewhat gracefully"""
        self._stop_publishers()

    @staticmethod
    def _queue_get_with_timeout(queue_proxy, timeout: float=0, stop_event: Event=None):
        """Queue get implementation that implements partial timeout for all Queue types including
        SimpleQueues.

        :raises queue.Empty
        """
        timer = Timer(interval=timeout)
        cycle_time = 0.005  # 5ms helps quickly iterate over SimpleQueues

        try:
            return queue_proxy.get(timeout=timeout)

        except TypeError:
            while True:
                # Asked to stop, so just stop
                if stop_event and stop_event.is_set():
                    return

                # Alternate timer
                if timer.interval():
                    raise Empty

                # Check if the queue has a get_nowait method, equivalent to get(timeout=0)
                # This probably won't be available if get(timeout=) failed, but checking anyway
                if hasattr(queue_proxy, "get_nowait"):
                    try:
                        return queue_proxy.get_nowait()
                    except Empty:
                        continue

                # SimpleQueues don't have a get_nowait method/mechanism
                else:
                    # Try not to get stuck, but can't guarantee that another thread hasn't
                    # grabbed one
                    if queue_proxy.empty():
                        time.sleep(cycle_time)
                        continue
                    else:
                        return queue_proxy.get()

    @staticmethod
    def _publisher(stop_event,
                   source_id,
                   source_queue,
                   dest_queues_dict,
                   timeout,
                   pipe_name=None):
        """Move messages from the source queue to the destination queue

        :param timeout=0.1; 100ms responsive-ish to shutdown and minimizes thrashing
        """
        # Make a helpful logger name
        if pipe_name is None:
            logger_name = "{}.publisher.{}".format(__name__, source_id)
        else:
            logger_name = "{}.publisher.{}.{}".format(__name__
                                                      , pipe_name
                                                      , source_id)

        log = logging.getLogger(logger_name)
        log.addHandler(logging.NullHandler())

        while True:
            # Check for stop
            if stop_event.is_set():
                log.info("Stopping due to stop event")
                return

            try:
                log.debug("Trying to get line from source in pair %s",
                          source_id)
                line = QueueLink._queue_get_with_timeout(source_queue,
                                                         timeout=timeout,
                                                         stop_event=stop_event)

                # Distribute the line to all downstream queues
                for dest_id, dest_queue in dest_queues_dict.items():
                    log.info("Writing line from source %s to dest %s",
                             source_id, dest_id)
                    dest_queue.put(line)

                # Mark that we've finished processing the item from the queue
                if hasattr(source_queue, 'task_done'):
                    source_queue.task_done()

            except Empty:
                log.debug("No lines to get from source in pair %s", source_id)

                if stop_event.is_set():
                    log.info("Stopping due to stop event")
                    return

            except EOFError:
                log.debug("Source in pair %s no longer available", source_id)

            except BrokenPipeError:
                log.debug("One pipe in pair %s is no longer available",
                          pipe_name if pipe_name else source_id)
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
    def register_queue(self, queue_proxy, direction: str, start_method: str=None) -> str:
        """Register a multiprocessing.JoinableQueue to this link

        For a new "source" queue, a publishing process will be created to send
        all additions down to destination queues.

        For a new "destination" queue, all new additions to "source" queues
        will be added to this queue.

        Returns the numeric ID for the new client, which must be used in all
        future interactions.

        Args:
            queue_proxy (QueueProxy): Proxy object to a JoinableQueue
            direction (string): source or destination
            start_method (string): How to start a process-based publisher (fork, forkserver, spawn)

        Returns:
            string. The client's ID for access to this queue

        """
        # Lowercase
        direction = direction.lower()
        op_direction = "destination" if direction == "source" else "source"

        # Warnings
        # Priority Queues
        if isinstance(queue_proxy, tuple(PRIORITY_QUEUES)):
            self._log.warning('Entries in a PriorityQueue must have the correct format (tuple or '
                           'simple class with a priority value) or the queue will block.')

        # SimpleQueues
        if isinstance(queue_proxy, tuple(SIMPLE_QUEUES)):
            self._log.warning('Using multiple readers on a SimpleQueue that is a source for a '
                           'QueueLink instance (including other QueueLink instances) can cause a '
                           'deadlock.')

        with self.queues_lock:
            # Get the queue list and opposite queue list
            queue_dict = getattr(self, "client_queues_{}"
                                 .format(direction))
            op_queue_dict = getattr(self, "client_queues_{}"
                                    .format(op_direction))

            # Make sure we don't accidentally create a loop, or add multiple
            # times
            if queue_proxy in queue_dict.values():
                raise ValueError("Cannot add this queue again")

            if queue_proxy in op_queue_dict.values():
                raise ValueError("This queue is in the opposite list. Cannot"
                                 " add to the {} list because it would cause"
                                 " a circular reference.".format(direction))

            # Increment the current queue_id
            queue_id = self.last_queue_id + 1
            self.last_queue_id = queue_id

            # Store the queue proxy in the appropriate queue list
            queue_dict[text(queue_id)] = queue_proxy

            # (Re)create the publishing processes
            # New source:
            #   Just add a new publishing process and send it the list of
            #   destinations.
            if direction == "source":
                self._log.debug("Registering source client")
                source_id = queue_id

                # Create and store a new stop event
                stop_event = Event()
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
                    self._start_publisher(source_id, start_method)

        return text(queue_id)

    def _start_publisher(self, source_id: str, start_method: str=None):
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
            process_name = "ClientPublisher-{}-{}".format(self.log_name,
                                                          source_id)
        else:
            process_name = "ClientPublisher-{}".format(source_id)

        # Determine whether to use a thread or process based publisher
        threaded = is_threaded([source_queue, *dest_queues_dict.values()])

        # Get the start context for a process-based startup, if not set use the system default
        if start_method or self.start_method:
            method = start_method if start_method else self.start_method
            Process_class = multiprocessing.get_context(method).Process
        else:
            Process_class = Process

        # Decide whether to use a local thread or process-based publisher
        Parallel = Thread if threaded or self.thread_only else Process_class

        # Start the publisher
        proc = Parallel(target=self._publisher,
                        name=process_name,
                        kwargs={"pipe_name": self.name,
                               "stop_event": stop_event,
                               "source_id": source_id,
                               "source_queue": source_queue,
                               "dest_queues_dict": dest_queues_dict,
                               "timeout": self.link_timeout})
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
    def unregister_queue(self, queue_id: Union[str, int], direction: str, start_method: str=None):
        """Detach a Queue proxy from this _QueuePipeAdapterBase

        Returns the clientId that was removed

        Args:
            queue_id (string): ID of the client
            direction (string): source or destination
            start_method (string): How to start a process-based publisher (fork, forkserver, spawn)

        Returns:
            string. ID of the client queue

        """
        # Lowercase
        direction = direction.lower()

        with self.queues_lock:
            queue_list = getattr(self,
                                 "client_queues_{}".format(direction))
            if text(queue_id) in queue_list:
                queue_list.pop(queue_id)

            if direction == "source":
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
                    self._start_publisher(source_id, start_method)

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
                if queue_id in self.client_queues_destination.keys():
                    self._log.debug("First checking upstream queue(s) of %s",
                                    queue_id)

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
            raise ProcessNotStarted("{} has not started".format(self.name))

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
    def destructive_audit(self, direction: str):
        """Print a line from each client Queue from the provided direction

        Args:
            direction (string): source or destination

        This is a destructive operation, as it *removes* a line from each Queue
        """
        direction = direction.lower()

        def get_nowait(queue_proxy):
            """Not all queues have a get_nowait method"""
            try:
                return queue_proxy.get_nowait()

            except AttributeError:
                # Try not to get stuck, but can't guarantee that another thread hasn't grabbed one
                if queue_proxy.empty():
                    raise Empty
                else:
                    return queue_proxy.get()

        with self.queues_lock:
            queue_list = getattr(self,
                                 "client_queues_{}".format(direction))

            for q_id in list(queue_list):
                try:
                    target_queue = self.get_queue(q_id)
                    self._log.info("queue_id %s: %s",
                                   text(q_id), get_nowait(target_queue))
                except Empty:
                    self._log.info("queue_id %s is empty", text(q_id))
