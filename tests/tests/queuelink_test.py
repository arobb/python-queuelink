# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
import logging
import os
import queue
import sys
import unittest
import multiprocessing

from multiprocessing import Manager
from parameterized import parameterized, parameterized_class
from queue import Empty

from tests.tests import context
from queuelink import Timer
from queuelink import QueueLink
from queuelink import DIRECTION
from queuelink.queuelink import is_threaded
from queuelink.common import PROC_START_METHODS, QUEUE_TYPE_LIST


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
        content_dir = os.path.join(os.path.dirname(__file__), '..', 'content')

        log_config_fname = os.path.join(content_dir, 'testing_logging_config.ini')
        logging.config.fileConfig(fname=log_config_fname, disable_existing_loggers=False)

        self.module = self.queue_type[0]
        self.class_name = self.queue_type[1]
        self.timeout = self.queue_type[2]

        self.multiprocessing_ctx = multiprocessing.get_context(self.start_method)
        self.manager = self.multiprocessing_ctx.Manager()

    def tearDown(self):
        self.manager.shutdown()

    def queue_factory(self):
        if self.module == 'queue':
            return getattr(queue, self.class_name)()

        if self.module == 'multiprocessing':
            return getattr(self.multiprocessing_ctx, self.class_name)()

        if self.module == 'manager':
            return getattr(self.manager, self.class_name)()

    def test_queuelink_get_client_id(self):
        queue_proxy = self.queue_factory()
        queue_link = QueueLink(name="test_link", start_method=self.start_method)
        client_id = queue_link.register_source(queue_proxy=queue_proxy)
        queue_link.close()

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

        source_id = queue_link.register_source(queue_proxy=source_q)
        dest_id = queue_link.register_destination(queue_proxy=dest_q)

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

        queue_link = QueueLink(name="test_link", start_method=self.start_method)

        source_id = queue_link.register_source(queue_proxy=source_q)
        dest_id = queue_link.register_destination(queue_proxy=dest_q)

        publisher = queue_link.client_pair_publishers[source_id]

        if hasattr(publisher, 'exitcode'):
            self.assertIsNone(publisher.exitcode)

        else:
            raise AttributeError(f'{type(publisher)} does not have attribute exitcode. Queue type '
                                 f'{self.module}.{self.class_name}')

        queue_link.stop()

    @parameterized.expand([
        [DIRECTION.FROM],
        [DIRECTION.TO]
    ])
    def test_queuelink_prevent_multiple_entries(self, direction):
        """Don't allow a user to add the same proxy to a direction multiple
        times."""
        q = self.queue_factory()

        queue_link = QueueLink(name="test_link", start_method=self.start_method)

        # Add the queue once
        queue_link.register_destination(queue_proxy=q)

        # Should raise an error the next time
        self.assertRaises(ValueError,
                          queue_link.register_queue,
                          queue_proxy=q,
                          direction=direction)

    @parameterized.expand([
        [DIRECTION.FROM, DIRECTION.TO],
        [DIRECTION.TO, DIRECTION.FROM]
    ])
    def test_queuelink_prevent_cyclic_graph(self,
                                            start_direction,
                                            end_direction):
        """Don't allow a user to add the same proxy to a direction multiple
        times."""
        q = self.queue_factory()
        queue_link = QueueLink(name="test_link", start_method=self.start_method)

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
        content_dir = os.path.join(os.path.dirname(__file__), '..', 'content')

        log_config_fname = os.path.join(content_dir, 'testing_logging_config.ini')
        logging.config.fileConfig(fname=log_config_fname, disable_existing_loggers=False)

        self.multiprocessing_ctx = multiprocessing.get_context(self.start_method)
        self.manager = self.multiprocessing_ctx.Manager()
        self.timeout = 60  # Some spawn instances needed a little more time
        self.test_text = "a😂" * 10

        self.source_info = {'module': self.source[0],
                            'class': self.source[1],
                            'max_size': self.source[2]}
        self.dest_info = {'module': self.dest[0],
                          'class': self.dest[1],
                          'max_size': self.dest[2]}

        self.source_class_path = f'{self.source_info["module"]}.{self.source_info["class"]}'
        self.dest_class_path = f'{self.dest_info["module"]}.{self.dest_info["class"]}'

    def queue_factory(self, module, class_name, max_size):
        if module == 'queue':
            queue_proxy =  getattr(queue, class_name)()

        if module == 'multiprocessing':
            queue_proxy =  getattr(self.multiprocessing_ctx, class_name)()

        if module == 'manager':
            queue_proxy = getattr(self.manager, class_name)()

        return queue_proxy

    def source_destination_movement(self, rounds: int=1):
        """Reusable source-destination method"""
        source_q_class = self.source_info['class']

        source_q = self.queue_factory(module=self.source_info['module'],
                                      class_name=self.source_info['class'],
                                      max_size=self.source_info['max_size'])
        dest_q = self.queue_factory(module=self.dest_info['module'],
                                    class_name=self.dest_info['class'],
                                    max_size=self.dest_info['max_size'])

        queue_link = QueueLink(source=source_q,
                               destination=dest_q,
                               name="movement_timing_test_link",
                               start_method=self.start_method,
                               link_timeout=self.timeout)

        text_in = self.test_text

        # Modify text to support Priority Queues
        tuple_in = (1, text_in)
        input = tuple_in if source_q_class == "PriorityQueue" else text_in

        timer = Timer(self.timeout)
        for i in range(rounds):
            source_q.put(input)

            # Pull the value
            while True:
                if timer.interval():
                    raise TimeoutError(f'Timeout for source {self.source_class_path}, '
                                        f'destination {self.dest_class_path}, and start '
                                        f'method {self.start_method}.')

                try:
                    object_out = QueueLink._queue_get_with_timeout(queue_proxy=dest_q,
                                                                   timeout=self.timeout)
                    text_out = object_out[1] if source_q_class == "PriorityQueue" else object_out

                    # Mark we pulled it for JoinableQueues
                    if hasattr(dest_q, 'task_done'):
                        dest_q.task_done()

                    # Move to the next item
                    break

                except Empty:
                    link_alive = queue_link.is_alive()

                    if link_alive:
                        if timer.interval():
                            raise Empty(f'Timeout for source {self.source_class_path}, '
                                        f'destination {self.dest_class_path}, and start '
                                        f'method {self.start_method}.')

                    else:
                        raise Empty('Destination queue is empty because the publisher process '
                                    f'has died for source {self.source_class_path}, destination '
                                    f'{self.dest_class_path}, and start '
                                    f'method {self.start_method}.')

        # Shut down publisher processes
        # Resolves:
        # Logging causing "ValueError: I/O operation on closed file"
        # Multiprocessing manager RemoteError/KeyErrors under certain conditions
        # Seemed to be with managed JoinableQueues and (threaded) queue.Queues
        queue_link.stop()

        # Retrieve metrics
        metrics = queue_link.get_metrics()

        return text_out, metrics

    def test_queuelink_source_destination_movement(self):
        text_in = self.test_text
        text_out, metrics = self.source_destination_movement(rounds=1)

        self.assertEqual(text_in,
                         text_out,
                         f"Text isn't the same across the link; source is {self.source_class_path} "
                         f"and dest is {self.dest_class_path}")

    def test_queuelink_500_movement_timing(self):
        rounds = 500
        threshold = 0.03

        text_out, metrics = self.source_destination_movement(rounds=rounds)

        self.assertLessEqual(metrics['mean'], threshold,
                             f'Mean latency for source {self.source_class_path} and destination '
                             f'{self.dest_class_path} and start method {self.start_method} exeeded '
                             f'threshold of {threshold} seconds.')


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkTestCaseCombinations)
    unittest.TextTestRunner(verbosity=2).run(suite)

    suite = unittest.TestLoader().loadTestsFromTestCase()
    unittest.TextTestRunner(verbosity=2).run(suite)
