# -*- coding: utf-8 -*-
"""Shared constants and functions"""
import queue
import multiprocessing
import random

from multiprocessing import queues as mp_queue_classes
from typing import List, Union

from multiprocessing.managers import BaseProxy

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