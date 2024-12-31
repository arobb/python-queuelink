# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
import sys
import unittest
import multiprocessing
from multiprocessing import Manager

from parameterized import parameterized, parameterized_class

# Python 2
if sys.version_info[0] == 2:
    import Queue as queue
    from Queue import Empty
else:
    import queue
    from queue import Empty

from tests.tests import context
from queuelink import Timer
from queuelink import QueueLink
from queuelink.queuelink import is_threaded

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

QUEUE_TYPE_LIST_SRC_DEST = itertools.product(QUEUE_TYPE_LIST, QUEUE_TYPE_LIST)

# Queue type list (just one) plus start methods
CARTESIAN_QUEUE_TYPES_START_LIST = itertools.product(QUEUE_TYPE_LIST,
                                                  PROC_START_METHODS)

# Queue type list for source and destination, plus start methods
CARTESIAN_SRC_DEST_START_LIST = itertools.product(QUEUE_TYPE_LIST,
                                                  QUEUE_TYPE_LIST,
                                                  PROC_START_METHODS)


@parameterized_class(('queue_type', 'start_method'), CARTESIAN_QUEUE_TYPES_START_LIST)
class QueueLinkTestCase(unittest.TestCase):
    """source and dest are tuples of (queue module, queue class, max timeout)

    These tests only check a single class, so we don't need both directions
    """
    def setUp(self):
        self.module = self.queue_type[0]
        self.class_name = self.queue_type[1]
        self.timeout = self.queue_type[2]

        self.multiprocessing_ctx = multiprocessing.get_context(self.start_method)
        self.manager = self.multiprocessing_ctx.Manager()

    def queue_factory(self):
        if self.module == 'queue':
            return getattr(queue, self.class_name)()

        if self.module == 'multiprocessing':
            return getattr(self.multiprocessing_ctx, self.class_name)()

        if self.module == 'manager':
            return getattr(self.manager, self.class_name)()

    def test_queuelink_get_client_id(self):
        queue_proxy = self.queue_factory()
        queue_link = QueueLink(name="test_link")
        client_id = queue_link.register_queue(queue_proxy=queue_proxy,
                                              direction="source")

        self.assertIsNotNone(client_id,
                             "register_queue did not return a client ID.")

        # Should be able to cast this to an int
        client_id_int = int(client_id)

        self.assertIsInstance(client_id_int,
                              int,
                              "register_queue did not return an int client ID.")

    def test_queuelink_verify_thread_only(self):
        """Make sure we always create a threaded publisher, even with process-based queues"""
        source_q = self.queue_factory()
        dest_q = self.queue_factory()
        queue_link = QueueLink(name="test_link", thread_only=True)

        source_id = queue_link.register_queue(queue_proxy=source_q,
                                              direction="source")
        dest_id = queue_link.register_queue(queue_proxy=dest_q,
                                              direction="destination")

        publisher = queue_link.client_pair_publishers[source_id]

        def get_exitcode(proc):
            return proc.exitcode

        self.assertRaises(AttributeError,
                          get_exitcode,
                          proc=publisher)

        queue_link.stop()

    def test_queuelink_verify_process_based(self):
        """Verify publishers are process-based when that is supported"""
        source_q = self.queue_factory()
        dest_q = self.queue_factory()

        # Skip the test if the queue is thread based
        if is_threaded(source_q):
            self.skipTest(f'Thread-based queue type {self.module}.{self.class_name}')

        queue_link = QueueLink(name="test_link")

        source_id = queue_link.register_queue(queue_proxy=source_q,
                                              direction="source")
        dest_id = queue_link.register_queue(queue_proxy=dest_q,
                                            direction="destination")

        publisher = queue_link.client_pair_publishers[source_id]

        if hasattr(publisher, 'exitcode'):
            self.assertIsNone(publisher.exitcode)

        else:
            raise AttributeError(f'{type(publisher)} does not have attribute exitcode. Queue type '
                                 f'{self.module}.{self.class_name}')

        queue_link.stop()

    @parameterized.expand([
        ["source"],
        ["destination"]
    ])
    def test_queuelink_prevent_multiple_entries(self, direction):
        """Don't allow a user to add the same proxy to a direction multiple
        times."""
        q = self.queue_factory()

        queue_link = QueueLink(name="test_link")

        # Add the queue once
        queue_link.register_queue(queue_proxy=q,
                                  direction=direction)

        # Should raise an error the next time
        self.assertRaises(ValueError,
                          queue_link.register_queue,
                          queue_proxy=q,
                          direction=direction)

    @parameterized.expand([
        ["source", "destination"],
        ["destination", "source"]
    ])
    def test_queuelink_prevent_cyclic_graph(self,
                                            start_direction,
                                            end_direction):
        """Don't allow a user to add the same proxy to a direction multiple
        times."""
        q = self.queue_factory()
        queue_link = QueueLink(name="test_link")

        # Add the queue once
        queue_link.register_queue(queue_proxy=q,
                                  direction=start_direction)

        # Should raise an error the next time
        self.assertRaises(ValueError,
                          queue_link.register_queue,
                          queue_proxy=q,
                          direction=end_direction)


@parameterized_class(('source', 'dest', 'start_method'), CARTESIAN_SRC_DEST_START_LIST)
class QueueLinkTestCaseCombinations(unittest.TestCase):
    """source and dest are tuples of (queue module, queue class, max timeout)"""
    def setUp(self):
        self.multiprocessing_ctx = multiprocessing.get_context(self.start_method)
        self.manager = self.multiprocessing_ctx.Manager()
        self.timeout = 2  # Some spawn instances needed a little more time

    def queue_factory(self, module, class_name, max_size):
        if module == 'queue':
            queue_proxy =  getattr(queue, class_name)()

        if module == 'multiprocessing':
            queue_proxy =  getattr(self.multiprocessing_ctx, class_name)()

        if module == 'manager':
            queue_proxy = getattr(self.manager, class_name)()

        return queue_proxy

    def test_queuelink_source_destination_movement(self):
        source_q_module = self.source[0]
        source_q_class = self.source[1]
        source_class_path = f'{source_q_module}.{source_q_class}'

        dest_q_module = self.dest[0]
        dest_q_class = self.dest[1]
        dest_class_path = f'{dest_q_module}.{dest_q_class}'

        source_q = self.queue_factory(module=source_q_module,
                                         class_name=source_q_class,
                                         max_size=self.source[2])
        dest_q = self.queue_factory(module=dest_q_module,
                                         class_name=dest_q_class,
                                         max_size=self.dest[2])

        queue_link = QueueLink(source=source_q,
                               destination=dest_q,
                               name="movement_test_link",
                               start_method=self.start_method,
                               link_timeout=self.timeout)

        text_in = "a😂" * 10

        # Modify text to support Priority Queues
        tuple_in = (1, text_in)
        source_q.put(tuple_in if source_q_class == "PriorityQueue" else text_in)

        # Pull the value
        try:
            object_out = QueueLink._queue_get_with_timeout(queue_proxy=dest_q, timeout=self.timeout)
            if source_q_class == "PriorityQueue":  # Test only needs this for source Priority q's
                text_out = object_out[1]
            else:
                text_out = object_out

        except Empty:
            raise Empty(f'Destination queue indicating empty for source {source_class_path}, '
            f'destination {dest_class_path}, and start method {self.start_method}')

        # Mark we pulled it for JoinableQueues
        if hasattr(dest_q, 'task_done'):
            dest_q.task_done()

        # Shut down publisher processes
        # Resolves:
        # Logging causing "ValueError: I/O operation on closed file"
        # Multiprocessing manager RemoteError/KeyErrors under certain conditions
        # Seemed to be with managed JoinableQueues and (threaded) queue.Queues
        queue_link.stop()

        self.assertEqual(text_in,
                         text_out,
                         f"Text isn't the same across the link; source is {source_class_path} "
                         f"and dest is {dest_class_path}")


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkTestCaseCombinations)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase()
    unittest.TextTestRunner(verbosity=2).run(suite)
