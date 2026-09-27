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
from queuelink import safe_get
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
        client_id = queue_link.read(q=queue_proxy)
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

        source_id = queue_link.read(q=source_q)
        dest_id = queue_link.write(q=dest_q)

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

        source_id = queue_link.read(q=source_q)
        dest_id = queue_link.write(q=dest_q)

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
        queue_link.write(q=q)

        # Should raise an error the next time
        self.assertRaises(ValueError,
                          queue_link.register_queue,
                          q=q,
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
        queue_link.register_queue(q=q,
                                  direction=start_direction)

        # Should raise an error the next time
        self.assertRaises(ValueError,
                          queue_link.register_queue,
                          q=q,
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
                               start_method=self.start_method)

        text_in = self.test_text

        # Modify text to support Priority Queues
        tuple_in = (1, text_in)
        input = tuple_in if source_q_class == "PriorityQueue" else text_in

        timer = Timer(self.timeout)
        for i in range(rounds):
            source_q.put(input)

            # Pull the value
            try:
                object_out = safe_get(queue_obj=dest_q, timeout=self.timeout)
                text_out = object_out[1] if source_q_class == "PriorityQueue" else object_out

                # Mark we pulled it for JoinableQueues
                if hasattr(dest_q, 'task_done'):
                    dest_q.task_done()

                # Move to the next item
                continue

            except Empty:
                link_alive = queue_link.is_alive()

                if link_alive:
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

    # TODO: Move this to throughput testing
    # def test_queuelink_500_movement_timing(self):
    #     rounds = 500
    #     threshold = 0.03
    #
    #     text_out, metrics = self.source_destination_movement(rounds=rounds)
    #
    #     self.assertLessEqual(metrics['mean'], threshold,
    #                          f'Mean latency for source {self.source_class_path} and destination '
    #                          f'{self.dest_class_path} and start method {self.start_method} exeeded '
    #                          f'threshold of {threshold} seconds.')


class QueueLinkMetricsIntegrationTest(unittest.TestCase):
    """Focused integration tests for QueueLink.get_metrics().

    Not parameterized over queue types — this tests the metrics pipeline,
    not queue-type compatibility.
    """

    def test_get_metrics_returns_data_after_stop(self):
        """get_metrics() returns a non-empty snapshot after publisher stops.

        The stop path always emits a final metrics snapshot, so even a single
        message is enough to generate data.
        """
        src = queue.Queue()
        dst = queue.Queue()
        ql = QueueLink(source=src, destination=dst)

        src.put('hello')
        safe_get(dst, timeout=5)
        ql.stop()

        metrics = ql.get_metrics()

        self.assertIsInstance(metrics, dict, "get_metrics() should return a dict")
        self.assertGreater(len(metrics), 0, "get_metrics() should be non-empty after stop")

        # Each value is a per-metric dict
        for eid, data in metrics.items():
            self.assertIsInstance(data, dict, f"element {eid} data should be a dict")

    def test_get_metrics_counting_data_after_messages(self):
        """After moving messages, the counting metric reflects the message count."""
        msg_count = 150  # exceeds metric_interval=100 to trigger a periodic emission
        src = queue.Queue()
        dst = queue.Queue()
        ql = QueueLink(source=src, destination=dst)

        for i in range(msg_count):
            src.put(f'msg_{i}')

        for _ in range(msg_count):
            safe_get(dst, timeout=10)

        ql.stop()
        metrics = ql.get_metrics()

        # Find the counting metric entry
        counting_data = [v for v in metrics.values() if 'count' in v]
        self.assertGreater(len(counting_data), 0,
                           "Expected at least one counting metric in get_metrics() result")

        total_count = counting_data[0]['count']
        self.assertGreaterEqual(total_count, msg_count,
                                f"Counting metric should reflect at least {msg_count} messages")

    def test_get_metrics_timing_data_after_messages(self):
        """After moving messages, the timing metric has a positive mean latency."""
        src = queue.Queue()
        dst = queue.Queue()
        ql = QueueLink(source=src, destination=dst)

        for i in range(5):
            src.put(f'msg_{i}')
        for _ in range(5):
            safe_get(dst, timeout=5)

        ql.stop()
        metrics = ql.get_metrics()

        timing_data = [v for v in metrics.values() if 'mean' in v]
        self.assertGreater(len(timing_data), 0,
                           "Expected at least one timing metric in get_metrics() result")
        self.assertGreater(timing_data[0]['mean'], 0,
                           "Timing metric mean should be positive")

    def test_get_metrics_returns_empty_dict_before_any_messages(self):
        """get_metrics() returns an empty dict when no messages have been moved."""
        src = queue.Queue()
        dst = queue.Queue()
        ql = QueueLink(source=src, destination=dst)

        # Don't send any messages; don't stop
        metrics = ql.get_metrics()
        self.assertEqual(metrics, {})

        ql.stop()

    def test_get_metrics_keyed_by_element_id_not_flat(self):
        """get_metrics() result must be keyed by element_id, not a flat merged dict.

        Bug 2 regression: the old implementation merged dicts by key, so two elements
        with a shared 'name' key would silently overwrite each other.
        """
        src = queue.Queue()
        dst = queue.Queue()
        ql = QueueLink(source=src, destination=dst)

        src.put('hello')
        safe_get(dst, timeout=5)
        ql.stop()

        metrics = ql.get_metrics()

        # Every key should map to a dict (element data), not a scalar
        for key, value in metrics.items():
            self.assertIsInstance(value, dict,
                                  f"Key '{key}' should map to a dict, got {type(value)}")


class QueueLinkMetricsProcessPublisherSpawnTest(unittest.TestCase):
    """Integration test for get_metrics() with a process-based publisher (spawn).

    Named with 'spawn' so tox routes it to the serial phase (forkserver/spawn tests
    cannot run under pytest-xdist fork workers).
    """

    def test_get_metrics_process_publisher_spawn(self):
        """get_metrics() returns data when the publisher is a separate process (spawn).

        Validates the _metrics_queue_process path end-to-end, including the feeder-thread
        flush that occurs before process exit.
        """
        ctx = multiprocessing.get_context('spawn')
        src = ctx.Queue()
        dst = ctx.Queue()
        ql = QueueLink(source=src, destination=dst, start_method='spawn')

        src.put('hello')
        safe_get(dst, timeout=30)
        ql.stop()

        metrics = ql.get_metrics()

        self.assertIsInstance(metrics, dict, "get_metrics() should return a dict")
        self.assertGreater(len(metrics), 0,
                           "get_metrics() should be non-empty after a process publisher stops")

        for eid, data in metrics.items():
            self.assertIsInstance(data, dict, f"element {eid} data should be a dict")


class QueueLinkDynamicDestinationTest(unittest.TestCase):
    """Tests for dynamic destination registration — adding destinations to a running QueueLink.

    Not parameterized over queue types; uses thread-based queues throughout.
    The behaviour under test is the stop-and-restart consistency guarantee in
    register_queue(direction=DIRECTION.TO), not queue-type compatibility.

    Consistency guarantee: after register_queue() returns, every message put to
    any source queue will be delivered to ALL registered destinations, including
    the one just added. Messages in-flight at the moment of registration are
    covered by the synchronous stop-and-join inside register_queue() — the
    stopping publisher finishes its current distribution step before exiting, so
    no message already dequeued from the source is lost.
    """

    TIMEOUT = 10

    def test_messages_reach_second_destination_after_dynamic_registration(self):
        """Messages put to source after registering a second destination arrive at both queues.

        queuelink.py: register_queue() stop-and-restart consistency guarantee.
        """
        src = queue.Queue()
        dst1 = queue.Queue()
        dst2 = queue.Queue()

        ql = QueueLink(source=src, destination=dst1)
        ql.register_queue(q=dst2, direction=DIRECTION.TO)

        src.put('hello')
        src.put('world')

        self.assertEqual('hello', safe_get(dst1, timeout=self.TIMEOUT))
        self.assertEqual('world', safe_get(dst1, timeout=self.TIMEOUT))
        self.assertEqual('hello', safe_get(dst2, timeout=self.TIMEOUT))
        self.assertEqual('world', safe_get(dst2, timeout=self.TIMEOUT))

        ql.stop()

    def test_link_remains_alive_after_dynamic_registration(self):
        """is_alive() returns True after registering a second destination.

        Verifies that the stop-and-restart inside register_queue() completes
        successfully and the publisher is running before the call returns.
        """
        src = queue.Queue()
        dst1 = queue.Queue()
        dst2 = queue.Queue()

        ql = QueueLink(source=src, destination=dst1)
        self.assertTrue(ql.is_alive())

        ql.register_queue(q=dst2, direction=DIRECTION.TO)
        self.assertTrue(ql.is_alive(),
                        "Publisher should be alive after dynamic destination registration")

        ql.stop()

    def test_existing_destination_unaffected_after_second_registered(self):
        """The first destination continues to receive messages after a second is added.

        Regression guard: the stop-and-restart must not lose the original destination.
        """
        src = queue.Queue()
        dst1 = queue.Queue()
        dst2 = queue.Queue()

        ql = QueueLink(source=src, destination=dst1)

        # Send and drain one message before adding dst2 to establish a clean baseline.
        src.put('before')
        self.assertEqual('before', safe_get(dst1, timeout=self.TIMEOUT))

        ql.register_queue(q=dst2, direction=DIRECTION.TO)

        src.put('after')
        self.assertEqual('after', safe_get(dst1, timeout=self.TIMEOUT),
                         "dst1 should still receive messages after dst2 is registered")
        self.assertEqual('after', safe_get(dst2, timeout=self.TIMEOUT),
                         "dst2 should receive messages after dynamic registration")

        ql.stop()

    def test_multiple_sequential_dynamic_registrations(self):
        """Adding three destinations one at a time — each addition keeps all previous ones live."""
        src = queue.Queue()
        dst1 = queue.Queue()
        dst2 = queue.Queue()
        dst3 = queue.Queue()

        ql = QueueLink(source=src, destination=dst1)
        ql.register_queue(q=dst2, direction=DIRECTION.TO)
        ql.register_queue(q=dst3, direction=DIRECTION.TO)

        src.put('broadcast')

        self.assertEqual('broadcast', safe_get(dst1, timeout=self.TIMEOUT))
        self.assertEqual('broadcast', safe_get(dst2, timeout=self.TIMEOUT))
        self.assertEqual('broadcast', safe_get(dst3, timeout=self.TIMEOUT))

        ql.stop()

    def test_multiple_sources_each_route_to_all_destinations_after_dynamic_registration(self):
        """With multiple sources, every publisher is restarted and routes to all destinations.

        Exercises the O(n) restart path — each of the n source publishers is
        individually stopped and restarted with the updated destination list.
        """
        src1 = queue.Queue()
        src2 = queue.Queue()
        dst1 = queue.Queue()
        dst2 = queue.Queue()

        ql = QueueLink()
        ql.register_queue(q=src1, direction=DIRECTION.FROM)
        ql.register_queue(q=src2, direction=DIRECTION.FROM)
        ql.register_queue(q=dst1, direction=DIRECTION.TO)

        # Adding dst2 triggers n=2 publisher restarts (one per source).
        ql.register_queue(q=dst2, direction=DIRECTION.TO)

        src1.put('from_src1')
        src2.put('from_src2')

        out_dst1 = {safe_get(dst1, timeout=self.TIMEOUT),
                    safe_get(dst1, timeout=self.TIMEOUT)}
        out_dst2 = {safe_get(dst2, timeout=self.TIMEOUT),
                    safe_get(dst2, timeout=self.TIMEOUT)}

        self.assertIn('from_src1', out_dst1,
                      "src1 message should reach dst1 after dynamic registration")
        self.assertIn('from_src2', out_dst1,
                      "src2 message should reach dst1 after dynamic registration")
        self.assertIn('from_src1', out_dst2,
                      "src1 message should reach dst2 after dynamic registration")
        self.assertIn('from_src2', out_dst2,
                      "src2 message should reach dst2 after dynamic registration")

        ql.stop()


class QueueLinkDynamicDestinationSpawnTest(unittest.TestCase):
    """Dynamic destination registration with a process-based (spawn) publisher.

    Named with 'spawn' so tox routes it to the serial phase (forkserver/spawn
    tests cannot run under pytest-xdist fork workers).

    For spawn publishers, the destination dict is serialised into the child
    process at start time. Separate memory means the parent's mutations to
    client_queues_destination are invisible to the running child. The
    stop-and-restart is therefore the only mechanism to deliver the updated
    destination list — these tests confirm it works end-to-end.
    """

    TIMEOUT = 30

    def test_messages_reach_new_destination_after_dynamic_registration_spawn(self):
        """Dynamic registration delivers subsequent messages to both destinations (spawn)."""
        ctx = multiprocessing.get_context('spawn')
        src = ctx.Queue()
        dst1 = ctx.Queue()
        dst2 = ctx.Queue()

        ql = QueueLink(source=src, destination=dst1, start_method='spawn')
        ql.register_queue(q=dst2, direction=DIRECTION.TO)

        self.assertTrue(ql.is_alive(),
                        "Publisher should be alive after dynamic destination registration (spawn)")

        src.put('hello')

        self.assertEqual('hello', safe_get(dst1, timeout=self.TIMEOUT))
        self.assertEqual('hello', safe_get(dst2, timeout=self.TIMEOUT))

        ql.stop()

    def test_existing_destination_unaffected_after_dynamic_registration_spawn(self):
        """The original destination still receives messages after a second is added (spawn)."""
        ctx = multiprocessing.get_context('spawn')
        src = ctx.Queue()
        dst1 = ctx.Queue()
        dst2 = ctx.Queue()

        ql = QueueLink(source=src, destination=dst1, start_method='spawn')

        src.put('before')
        self.assertEqual('before', safe_get(dst1, timeout=self.TIMEOUT))

        ql.register_queue(q=dst2, direction=DIRECTION.TO)

        src.put('after')
        self.assertEqual('after', safe_get(dst1, timeout=self.TIMEOUT),
                         "dst1 should still receive messages after dst2 is registered (spawn)")
        self.assertEqual('after', safe_get(dst2, timeout=self.TIMEOUT),
                         "dst2 should receive messages after dynamic registration (spawn)")

        ql.stop()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkTestCaseCombinations)
    unittest.TextTestRunner(verbosity=2).run(suite)
