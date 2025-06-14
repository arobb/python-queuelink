# -*- coding: utf-8 -*-
"""Shared constants and functions"""
import queue
import random
import time

from enum import Enum
from os import PathLike
from queue import Empty
from threading import Event as t_Event
from threading import Lock as t_Lock
from typing import IO, List, Union

# Multiprocessing imports
import multiprocessing
from multiprocessing import Event as mp_Event
from multiprocessing import Lock as mp_Lock
from multiprocessing import queues as mp_queue_classes
from multiprocessing.managers import BaseProxy

# Internal imports; keep to minimum to prevent cyclical dependencies
from .timer import Timer

class DIRECTION(Enum):
    """Directions enum (from source/to destination)"""
    def __str__(self):
        return str(self.value)

    FROM = 'source'
    TO = 'destination'

# Supported events
UNION_SUPPORTED_EVENTS = Union[
    t_Event,
    mp_Event,
    BaseProxy
]

# Supported locks
UNION_SUPPORTED_LOCKS = Union[
    t_Lock,
    mp_Lock,
    BaseProxy
]

# Ways to start a process
PROC_START_METHODS = ['fork', 'forkserver', 'spawn']

# Module, Class, Max size
QUEUE_TYPE_LIST = [
    ('manager', 'Queue', None),
    ('manager', 'JoinableQueue', None),
    ('multiprocessing', 'Queue', None),
    ('multiprocessing', 'JoinableQueue', None),
    ('multiprocessing', 'SimpleQueue', None),
    ('queue', 'Queue', None),
    ('queue', 'LifoQueue', None),
    ('queue', 'PriorityQueue', None),
    ('queue', 'SimpleQueue', None)
]

# List of queue types that are threaded (vs multiprocessing)
THREADED_QUEUES = [
    queue.Queue,
    queue.LifoQueue,
    queue.PriorityQueue,
    queue.SimpleQueue
]

# List of PriorityQueue types
PRIORITY_QUEUES = [
    queue.PriorityQueue
]

# List of SimpleQueue types
SIMPLE_QUEUES = [
    queue.SimpleQueue,
    mp_queue_classes.SimpleQueue
]

UNION_MULTIPROCESSING_QUEUES = Union[
    multiprocessing.queues.Queue,
    multiprocessing.queues.JoinableQueue,
    multiprocessing.queues.SimpleQueue
]

# Union type for typing support
# pylint: disable=invalid-name
UNION_SUPPORTED_QUEUES = Union[
    queue.Queue,
    queue.LifoQueue,
    queue.PriorityQueue,
    queue.SimpleQueue,
    multiprocessing.queues.Queue,
    multiprocessing.queues.JoinableQueue,
    multiprocessing.queues.SimpleQueue,
    BaseProxy
]

# Union type for IO (reader/writer)
# pylint: disable=invalid-name
UNION_SUPPORTED_IO_TYPES = Union[
    IO,
    str,
    PathLike
]

# Union type for file pointer types (reader/writer)
# pylint: disable=invalid-name
UNION_SUPPORTED_PATH_TYPES = Union[
    str,
    PathLike
]


def is_threaded(queue_list: Union[List, UNION_SUPPORTED_QUEUES]) -> bool:
    """Check whether one or more queues are threaded

    Args:
         queue_list: Any queue or list of queues (any type)

    Returns:
        True if any queue in the given list is threaded.
    """
    if not isinstance(queue_list, list):
        queue_list = [queue_list]

    for q_inst in queue_list:
        if isinstance(q_inst, tuple(THREADED_QUEUES)):
            return True

    return False

def new_id() -> str:
    """Create a reasonably unique ID string.

    Returns:
        A 6-character unique ID.
    """
    return ''.join([random.choice(  # nosec
               '0123456789ABCDEF') for x in range(6)])

def safe_get(queue_obj: UNION_SUPPORTED_QUEUES,
             block: bool = True,
             timeout: float = 0,
             stop_event: Union[t_Event, mp_Event] = None,
             cycle_time: float = 0.005) -> any:
    """Queue ``get`` implementation that implements partial timeout for all Queue types including
    SimpleQueues.

    CAUTION: Can deadlock if a SimpleQueue is read by multiple consumers.

    Args:
        queue_obj: Any queue object
        block: Block until queue has an element to return (default True)
        timeout: Timeout in seconds; if block is True, raise Empty after this duration
        stop_event: Event to force stop
        cycle_time: Cycle time in seconds of blocking logic for SimpleQueues

    Returns:
        Returns a queue element or None

    Raises:
        queue.Empty
    """
    timer = Timer(interval=timeout)

    # Handle cycle time with the stop_event if present
    def wait(time_out: float=0):
        """Return False when timeout expires or True if the stop_event is set

        Args:
            time_out: Timeout in seconds

        Returns:
            False when timeout expires or True if the stop_event is set
        """
        if not stop_event:
            time.sleep(time_out)
            return False

        return stop_event.wait(time_out)

    try:
        return queue_obj.get(timeout=timeout)

    # get(block=, timeout=) method signature doesn't exist for SimpleQueues
    # Alternative implementation to simulate the behavior
    except TypeError:
        while True:
            # Asked to stop, so just stop
            if stop_event and stop_event.is_set():
                raise Empty

            # Alternate timer
            if timer.interval():
                raise Empty

            # Check if the queue has a get_nowait method, equivalent to get(block=False)
            # This probably won't be available if get(timeout=) failed, but checking anyway
            if hasattr(queue_obj, "get_nowait"):
                try:
                    return queue_obj.get_nowait()

                except Empty:
                    if not block:
                        raise Empty

                    if wait(time_out=cycle_time):  # True if stop event was set
                        raise Empty

                    continue

                except (EOFError, BrokenPipeError):
                    raise Empty

            # SimpleQueues don't have a get_nowait method/mechanism
            # Try not to get stuck, but can't guarantee that another thread hasn't
            # grabbed one
            if queue_obj.empty():
                if not block:
                    raise Empty

                if wait(cycle_time):  # True if stop event was set
                    # Raise empty if the stop_event is set to break out of the loop
                    raise Empty

                # Timeout happened, begin the next while cycle
                continue

            # SimpleQueue with an item in the queue
            # This can deadlock if there's another reader of this same queue
            try:
                return queue_obj.get()
            except (EOFError, BrokenPipeError):
                raise Empty

    except (EOFError, BrokenPipeError):
        raise Empty

    finally:
        queue_obj = None
        stop_event = None
