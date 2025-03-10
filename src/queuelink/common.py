# -*- coding: utf-8 -*-
"""Shared constants and functions"""
import queue
import random
import time

from enum import Enum
from queue import Empty
from threading import Event as t_Event
from typing import List, Union

# Multiprocessing imports
import multiprocessing
from multiprocessing import Event as mp_Event
from multiprocessing import queues as mp_queue_classes
from multiprocessing.managers import BaseProxy

# Internal imports; keep to minimum to prevent cyclical dependencies
from .timer import Timer

# Directions (source/destination)
class DIRECTION(Enum):
    def __str__(self):
        return str(self.value)

    FROM = 'source'
    TO = 'destination'

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

# Union type for typing support
UNION_SUPPORTED_QUEUES = Union[queue.Queue,
                               queue.LifoQueue,
                               queue.PriorityQueue,
                               queue.SimpleQueue,
                               multiprocessing.queues.Queue,
                               multiprocessing.queues.JoinableQueue,
                               multiprocessing.queues.SimpleQueue,
                               BaseProxy]


def is_threaded(queue_list: Union[List, UNION_SUPPORTED_QUEUES]):
    """Check whether one or more queues are threaded

    :param queue: Any queue or list of queues (any type)
    :return bool
    """
    if not isinstance(queue_list, list):
        queue_list = [queue_list]

    for q_inst in queue_list:
        if isinstance(q_inst, tuple(THREADED_QUEUES)):
            return True

    return False

def new_id():
    return ''.join([random.choice(  # nosec
               '0123456789ABCDEF') for x in range(6)])

def safe_get(queue_proxy, timeout: float=0, stop_event: Union[t_Event, mp_Event]=None):
    """Queue get implementation that implements partial timeout for all Queue types including
    SimpleQueues.

    :raises queue.Empty
    """
    timer = Timer(interval=timeout)
    cycle_time = 0.005  # 5ms helps quickly iterate over SimpleQueues

    # Handle cycle time with the stop_event if present
    def wait(time_out=0):
        if not stop_event:
            time.sleep(time_out)
            return False
        else:
            return stop_event.wait(time_out)

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

            # Check if the queue has a get_nowait method, equivalent to get(block=False)
            # This probably won't be available if get(timeout=) failed, but checking anyway
            if hasattr(queue_proxy, "get_nowait"):
                try:
                    return queue_proxy.get_nowait()
                except Empty:
                    if wait(cycle_time):  # True if stop event was set
                        return
                    else:
                        continue

            # SimpleQueues don't have a get_nowait method/mechanism
            # Try not to get stuck, but can't guarantee that another thread hasn't
            # grabbed one
            if queue_proxy.empty():
                if wait(cycle_time):  # True if stop event was set
                    return
                else:  # Timeout happened, begin the next while cycle
                    continue

            # SimpleQueue with an item in the queue
            # This can deadlock if there's another reader of this same queue
            return queue_proxy.get()

    finally:
        stop_event = None