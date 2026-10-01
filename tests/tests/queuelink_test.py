# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools
import logging
import os
import queue
import sys
import threading
import time
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


class QueueLinkIntQueueIdTest(unittest.TestCase):
    """Regression tests for FEAT-010 bug 3: get_queue() / is_empty() must accept
    an int queue_id, matching the ``Union[str, int]`` type hint both methods
    already declare.

    Not parameterized over queue types — this tests id normalization, not
    queue-type compatibility.
    """

    def test_get_queue_accepts_int_id(self):
        """get_queue(int(sid)) returns the same queue registered with read()."""
        q = queue.Queue()
        ql = QueueLink(name='int-id-test', thread_only=True)
        sid = ql.read(q=q)

        self.assertIs(ql.get_queue(int(sid)), q)

        ql.stop()

    def test_is_empty_accepts_int_id(self):
        """is_empty(int(sid)) reports the same result as is_empty(str(sid))."""
        q = queue.Queue()
        ql = QueueLink(name='int-id-test', thread_only=True)
        sid = ql.read(q=q)

        self.assertTrue(ql.is_empty(int(sid)))

        q.put('not empty anymore')
        self.assertFalse(ql.is_empty(int(sid)))

        ql.stop()

    def test_unregister_queue_unknown_source_id_does_not_raise(self):
        """unregister_queue(FROM) with an id never registered must not raise KeyError.

        Regression guard for the same fix (010-1-2): publisher_stops.pop()
        used to raise KeyError for an id that was never registered.
        """
        ql = QueueLink(name='int-id-test', thread_only=True)

        result = ql.unregister_queue(queue_id='does-not-exist', direction=DIRECTION.FROM)
        self.assertEqual('does-not-exist', result)

        ql.stop()


class QueueLinkEOFErrorTest(unittest.TestCase):
    """Regression test for FEAT-010 bug 5: _publisher must exit instead of
    busy-looping when a destination's put() raises EOFError.
    """

    class _EOFOnPutQueue:
        """Minimal queue-like stub whose put() always raises EOFError."""

        def put(self, item):  # pylint: disable=unused-argument
            raise EOFError('destination gone')

        def empty(self):
            return True

    def test_publisher_exits_when_destination_put_raises_eoferror(self):
        """The publisher thread stops (is_alive() False) after a destination
        raises EOFError on put(), instead of looping forever."""
        src = queue.Queue()
        dst = self._EOFOnPutQueue()
        ql = QueueLink(source=src, destination=dst, thread_only=True)

        src.put('trigger')

        publisher = list(ql.client_pair_publishers.values())[0]

        timeout_timer = Timer(interval=10)
        while publisher.is_alive():
            if timeout_timer.interval():
                ql.stop()
                self.fail('Publisher did not exit after destination raised EOFError')

            time.sleep(0.01)

        self.assertFalse(publisher.is_alive())


class QueueLinkDirectionStrTest(unittest.TestCase):
    """Regression tests for FEAT-010 bug 6: direction validation must accept
    DIRECTION's string values and behave identically across Python versions.

    Before the fix, ``"source" in DIRECTION`` raised TypeError on Python
    3.9-3.11 but returned a bool on 3.12+ (Enum.__contains__ semantics
    changed), so passing a string was accepted or rejected depending on the
    interpreter version. validate_direction now converts via
    ``DIRECTION(value)``, which is version-independent.
    """

    def test_register_queue_accepts_source_string(self):
        q = queue.Queue()
        ql = QueueLink(name='dir-str-test', thread_only=True)

        client_id = ql.register_queue(q=q, direction='source')
        self.assertIn(client_id, ql.client_queues_source)

        ql.stop()

    def test_register_queue_accepts_destination_string(self):
        q = queue.Queue()
        ql = QueueLink(name='dir-str-test', thread_only=True)

        client_id = ql.register_queue(q=q, direction='destination')
        self.assertIn(client_id, ql.client_queues_destination)

        ql.stop()

    def test_register_queue_rejects_invalid_string_with_value_error(self):
        q = queue.Queue()
        ql = QueueLink(name='dir-str-test', thread_only=True)

        with self.assertRaises(ValueError):
            ql.register_queue(q=q, direction='not-a-direction')

        ql.stop()


def _call_within(test_case, func, bound, message):
    """Run ``func`` in a daemon thread; fail ``test_case`` if it does not return
    within ``bound`` seconds (instead of hanging the test run)."""
    caller = threading.Thread(target=func, daemon=True)
    caller.start()
    caller.join(timeout=bound)

    if caller.is_alive():
        test_case.fail(message)


def _wait_until_blocked_on_full_destination(test_case, dest, settle=0.5, bound=30):
    """Wait until ``dest`` is full, then give the publisher time to pick up the next
    source item and block trying to put it."""
    timeout_timer = Timer(interval=bound)
    while not dest.full():
        if timeout_timer.interval():
            test_case.fail('Destination never filled up')

        time.sleep(0.01)

    time.sleep(settle)


class QueueLinkFullDestinationStopTest(unittest.TestCase):
    """Regression tests for FEAT-010 bug 1: a publisher blocked putting to a full,
    unconsumed destination must still stop.

    Before the fix, ``dest_queue.put(line)`` had no timeout, so ``stop()`` (and
    ``register_queue(TO)``, which stops every publisher first) looped on
    ``join(timeout=1)`` forever. Thread publishers; see
    ``QueueLinkFullDestinationStopProcessTest`` for process publishers.
    """

    STOP_BOUND = 3  # Seconds

    def test_stop_returns_with_full_destination(self):
        """stop() returns promptly while the publisher is blocked on a full destination,
        and only the item the destination had room for was delivered."""
        src = queue.Queue()
        dst = queue.Queue(maxsize=1)
        ql = QueueLink(source=src, destination=dst, name='full-dest')

        for i in range(3):
            src.put(f'item-{i}')

        _wait_until_blocked_on_full_destination(self, dst)
        publisher = list(ql.client_pair_publishers.values())[0]

        with self.assertLogs('queuelink.queuelink.publisher', level='WARNING') as logs:
            _call_within(self, ql.stop, self.STOP_BOUND,
                         'stop() hung on a publisher blocked by a full destination')

        self.assertFalse(publisher.is_alive())
        self.assertIn('abandoned for 1 of 1 destination', '\n'.join(logs.output))

        # item-0 delivered, item-1 abandoned, item-2 never taken from the source
        self.assertEqual('item-0', dst.get_nowait())
        self.assertTrue(dst.empty())
        self.assertEqual('item-2', src.get_nowait())

        # task_done() was called for both items taken from the source (delivered and
        # abandoned); only item-2, just removed above without task_done(), remains
        self.assertEqual(1, src.unfinished_tasks)

    def test_register_destination_returns_with_full_destination(self):
        """register_queue(TO) stops every publisher first; it must return promptly
        while a publisher is blocked on a full destination."""
        src = queue.Queue()
        dst = queue.Queue(maxsize=1)
        new_dst = queue.Queue()
        ql = QueueLink(source=src, destination=dst, name='full-dest')

        for i in range(3):
            src.put(f'item-{i}')

        _wait_until_blocked_on_full_destination(self, dst)

        _call_within(self, lambda: ql.register_queue(q=new_dst, direction=DIRECTION.TO),
                     self.STOP_BOUND,
                     'register_queue(TO) hung on a publisher blocked by a full destination')

        self.assertIn(new_dst, ql.client_queues_destination.values())
        self.assertTrue(ql.is_alive())

        # The restarted publisher is blocked on the still-full dst again; stop must
        # still return
        _call_within(self, ql.stop, self.STOP_BOUND,
                     'stop() hung after register_queue(TO) on a full destination')

    def test_partial_fan_out_delivers_to_destinations_with_room(self):
        """On stop, only the full destination is abandoned; a destination with room
        still receives the item."""
        src = queue.Queue()
        dst_full = queue.Queue(maxsize=1)
        dst_open = queue.Queue()
        ql = QueueLink(source=src, destination=[dst_full, dst_open], name='full-dest')

        for i in range(3):
            src.put(f'item-{i}')

        _wait_until_blocked_on_full_destination(self, dst_full)

        _call_within(self, ql.stop, self.STOP_BOUND,
                     'stop() hung on a publisher blocked by a full destination')

        self.assertEqual('item-0', dst_full.get_nowait())
        self.assertTrue(dst_full.empty())

        # dst_open is fanned out to after dst_full (registration order), so it gets
        # item-1 after dst_full is abandoned
        self.assertEqual('item-0', dst_open.get_nowait())
        self.assertEqual('item-1', dst_open.get_nowait())
        self.assertTrue(dst_open.empty())


# Bounded process-capable queue types (Module, Class, Max size).
# multiprocessing.SimpleQueue cannot be bounded, so it is not included.
BOUNDED_PROCESS_QUEUE_TYPES = [
    ('manager', 'Queue', 1),
    ('manager', 'JoinableQueue', 1),
    ('multiprocessing', 'Queue', 1),
    ('multiprocessing', 'JoinableQueue', 1)
]


@parameterized_class(('queue_type', 'start_method'),
                     itertools.product(BOUNDED_PROCESS_QUEUE_TYPES, PROC_START_METHODS))
class QueueLinkFullDestinationStopProcessTest(unittest.TestCase):
    """Process-publisher variant of ``QueueLinkFullDestinationStopTest`` (FEAT-010
    bug 1), for each bounded process queue type and start method."""

    STOP_BOUND = 3  # Seconds

    def setUp(self):
        self.module = self.queue_type[0]
        self.class_name = self.queue_type[1]
        self.max_size = self.queue_type[2]

        self.multiprocessing_ctx = multiprocessing.get_context(self.start_method)
        self.manager = None

        if self.module == 'manager':
            self.manager = self.multiprocessing_ctx.Manager()

    def tearDown(self):
        if self.manager is not None:
            self.manager.shutdown()

    def queue_factory(self, bounded=False):
        maxsize = self.max_size if bounded else 0

        if self.module == 'multiprocessing':
            return getattr(self.multiprocessing_ctx, self.class_name)(maxsize=maxsize)

        if self.module == 'manager':
            return getattr(self.manager, self.class_name)(maxsize=maxsize)

    def test_stop_returns_with_full_destination(self):
        """stop() returns promptly while a process publisher is blocked on a full
        destination."""
        src = self.queue_factory()
        dst = self.queue_factory(bounded=True)
        ql = QueueLink(source=src, destination=dst, start_method=self.start_method)

        publisher = list(ql.client_pair_publishers.values())[0]
        self.assertFalse(isinstance(publisher, threading.Thread),
                         'Expected a process-based publisher')

        for i in range(3):
            src.put(f'item-{i}')

        _wait_until_blocked_on_full_destination(self, dst)

        _call_within(self, ql.stop, self.STOP_BOUND,
                     'stop() hung on a process publisher blocked by a full destination')

        self.assertFalse(publisher.is_alive())
        self.assertEqual('item-0', safe_get(dst, timeout=5))

    def test_register_destination_returns_with_full_destination(self):
        """register_queue(TO) returns promptly while a process publisher is blocked on
        a full destination."""
        src = self.queue_factory()
        dst = self.queue_factory(bounded=True)
        new_dst = self.queue_factory()
        ql = QueueLink(source=src, destination=dst, start_method=self.start_method)

        for i in range(3):
            src.put(f'item-{i}')

        _wait_until_blocked_on_full_destination(self, dst)

        _call_within(self, lambda: ql.register_queue(q=new_dst, direction=DIRECTION.TO),
                     self.STOP_BOUND,
                     'register_queue(TO) hung on a process publisher blocked by a full '
                     'destination')

        _call_within(self, ql.stop, self.STOP_BOUND,
                     'stop() hung after register_queue(TO) on a full destination')


def _produce_items(q, items):
    """Producer-process target: put ``items`` on ``q``. The producer's exit flushes its
    feeder thread, so once the process is joined every item is in ``q``'s pipe and
    ``q.empty()`` in the parent reliably means "consumed"."""
    for item in items:
        q.put(item)


# multiprocessing queue types whose put() goes through a per-process feeder thread
# (Module, Class)
FEEDER_THREAD_QUEUE_TYPES = [
    ('multiprocessing', 'Queue'),
    ('multiprocessing', 'JoinableQueue')
]


@parameterized_class(('queue_type', 'start_method'),
                     itertools.product(FEEDER_THREAD_QUEUE_TYPES, PROC_START_METHODS))
class QueueLinkUnreadDestinationStopProcessTest(unittest.TestCase):
    """Regression test for FEAT-010 Q5: a process publisher whose *unbounded*
    destination nobody reads must still stop.

    The destination never blocks ``put()``, so the FEAT-010 bug 1 fix does not apply.
    Instead the publisher's own feeder thread buffers everything the OS pipe cannot
    take. Before the fix the publisher process blocked at exit joining that feeder
    thread, so ``stop()`` looped on ``join(timeout=1)`` forever.

    Run for every start method, not just fork. The hang is in the child's exit path,
    and that path differs by start method (``os._exit`` after a fork vs. the
    spawn/forkserver bootstrap). The hang was reproduced manually under all three.
    Each case takes about a second.
    """

    STOP_BOUND = 3  # Seconds
    ITEM_COUNT = 64  # 64 x 4 KiB = 256 KiB, well past a 64 KiB OS pipe buffer

    def test_stop_returns_with_unread_unbounded_destination(self):
        """stop() returns promptly when an unbounded destination holds more unread
        data than the OS pipe buffer."""
        ctx = multiprocessing.get_context(self.start_method)
        src = getattr(ctx, self.queue_type[1])()
        dst = getattr(ctx, self.queue_type[1])()
        ql = QueueLink(source=src, destination=dst, start_method=self.start_method)

        publisher = list(ql.client_pair_publishers.values())[0]
        self.assertFalse(isinstance(publisher, threading.Thread),
                         'Expected a process-based publisher')

        producer = ctx.Process(target=_produce_items,
                               args=(src, [f'{i:04d}' + 'x' * 4092
                                           for i in range(self.ITEM_COUNT)]))
        producer.start()
        producer.join()

        # Wait until the publisher has taken everything from the source, so the
        # overflow is sitting in its feeder-thread buffer
        timeout_timer = Timer(interval=30)
        while not src.empty():
            if timeout_timer.interval():
                self.fail('Publisher never drained the source')

            time.sleep(0.01)

        time.sleep(0.5)

        _call_within(self, ql.stop, self.STOP_BOUND,
                     'stop() hung on a process publisher with an unread, unbounded '
                     'destination')

        self.assertFalse(publisher.is_alive())

        # Whatever reached the pipe is still readable, in order
        self.assertTrue(safe_get(dst, timeout=5).startswith('0000'))


class QueueLinkStopFlushesDestinationTest(unittest.TestCase):
    """The FEAT-010 Q5 fix must not drop items that a *read* destination can still
    accept when the publisher stops.

    ``cancel_join_thread()`` on its own drops everything still in the publisher's
    feeder-thread buffer at exit. With a consumer reading slower than the publisher
    writes, that lost hundreds of items in about 1 run in 5 when this was checked
    manually. The fix first lets the buffer flush, with a time limit. Fork only: this
    checks the flush-before-cancel logic, which does not depend on the start method.

    The loss is timing-dependent, so this test catches a cancel-only fix in about
    half of runs, not every run. It passes reliably with the bounded flush.
    """

    ITEM_COUNT = 3000
    ROUNDS = 3

    def test_stop_delivers_everything_taken_from_the_source(self):
        """Every item the publisher took from the source reaches an actively read
        destination after stop()."""
        ctx = multiprocessing.get_context('fork')
        payload = 'x' * 4096

        for _ in range(self.ROUNDS):
            src = ctx.Queue()
            dst = ctx.Queue()
            ql = QueueLink(source=src, destination=dst, start_method='fork')

            received = []

            def consume(dst=dst, received=received):
                while True:
                    try:
                        received.append(dst.get(timeout=2))
                    except queue.Empty:
                        return

            consumer = threading.Thread(target=consume, daemon=True)
            consumer.start()

            producer = ctx.Process(target=_produce_items,
                                   args=(src, [(i, payload)
                                               for i in range(self.ITEM_COUNT)]))
            producer.start()
            producer.join()

            timeout_timer = Timer(interval=60)
            while not src.empty():
                if timeout_timer.interval():
                    self.fail('Publisher never drained the source')

                time.sleep(0.0005)

            ql.stop()
            consumer.join(timeout=60)

            self.assertEqual(list(range(self.ITEM_COUNT)), [i for i, _ in received])


class QueueLinkThreadPublisherLeavesDestinationOpenTest(unittest.TestCase):
    """The FEAT-010 Q5 fix must only touch a process publisher's own copies of its
    destinations. A thread publisher shares the caller's queue objects, so closing
    them or cancelling their feeder join would break the caller's queue."""

    def test_multiprocessing_destination_usable_after_thread_publisher_stops(self):
        src = queue.Queue()  # A threading source forces a thread publisher
        dst = multiprocessing.get_context('fork').Queue()
        ql = QueueLink(source=src, destination=dst)

        publisher = list(ql.client_pair_publishers.values())[0]
        self.assertTrue(isinstance(publisher, threading.Thread),
                        'Expected a thread-based publisher')

        src.put('via-link')
        self.assertEqual('via-link', safe_get(dst, timeout=5))

        ql.stop()

        # Raises ValueError("Queue ... is closed") if the publisher closed it
        dst.put('after-stop')
        self.assertEqual('after-stop', safe_get(dst, timeout=5))


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkTestCaseCombinations)
    unittest.TextTestRunner(verbosity=2).run(suite)
