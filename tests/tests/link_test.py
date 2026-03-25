# -*- coding: utf-8 -*-
"""Tests for queuelink.link() factory function.

Style: focused unit/example tests (style 2 per AGENTS.md). The full
parameterized matrix is avoided since link() abstracts queue-type and
start-method complexity. The matrix is used only where start method is
expected to affect behaviour (spawn/forkserver SemLock regression tests).
"""
import io
import logging
import logging.config
import multiprocessing
import os
import queue
import tempfile
import time
import unittest

from subprocess import Popen, PIPE

from tests.tests import context  # noqa: F401  — configures sys.path and logging
from queuelink import link
from queuelink.link import _LinkResult
from queuelink.queuelink import QueueLink


TEXT = "hello queuelink 😊"
TIMEOUT = 10


def _get_log_config():
    content_dir = os.path.join(os.path.dirname(__file__), '..', 'content')
    return os.path.join(content_dir, 'testing_logging_config.ini')


class LinkQueueToQueueTest(unittest.TestCase):
    """queue → queue: should produce a QueueLink."""

    def setUp(self):
        logging.config.fileConfig(fname=_get_log_config(), disable_existing_loggers=False)

    def test_returns_link_result(self):
        src = queue.Queue()
        dst = queue.Queue()
        result = link(src, dst)
        self.assertIsInstance(result, _LinkResult)
        result.stop()

    def test_queue_link_is_set(self):
        src = queue.Queue()
        dst = queue.Queue()
        result = link(src, dst)
        self.assertIsNotNone(result.queue_link)
        self.assertIsInstance(result.queue_link, QueueLink)
        result.stop()

    def test_data_flows_queue_to_queue(self):
        src = queue.Queue()
        dst = queue.Queue()
        result = link(src, dst)
        src.put(TEXT)
        out = dst.get(timeout=TIMEOUT)
        self.assertEqual(TEXT, out)
        result.stop()

    def test_fan_out_queue_to_multiple_queues(self):
        src = queue.Queue()
        dst1 = queue.Queue()
        dst2 = queue.Queue()
        result = link(src, [dst1, dst2])
        src.put(TEXT)
        out1 = dst1.get(timeout=TIMEOUT)
        out2 = dst2.get(timeout=TIMEOUT)
        self.assertEqual(TEXT, out1)
        self.assertEqual(TEXT, out2)
        result.stop()

    def test_is_alive_true_while_running(self):
        src = queue.Queue()
        dst = queue.Queue()
        result = link(src, dst)
        self.assertTrue(result.is_alive())
        result.stop()

    def test_stop_terminates_workers(self):
        src = queue.Queue()
        dst = queue.Queue()
        result = link(src, dst)
        result.stop()
        # Give workers a moment to shut down
        deadline = time.monotonic() + 5
        while result.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(result.is_alive())

    def test_close_alias_for_stop(self):
        src = queue.Queue()
        dst = queue.Queue()
        result = link(src, dst)
        result.close()   # should not raise
        deadline = time.monotonic() + 5
        while result.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(result.is_alive())


class LinkHandleToQueueTest(unittest.TestCase):
    """handle/path/Connection → queue: should produce a reader adapter."""

    def setUp(self):
        logging.config.fileConfig(fname=_get_log_config(), disable_existing_loggers=False)

    def test_subprocess_stdout_to_queue(self):
        dst = queue.Queue()
        proc = Popen(['echo', '-n', TEXT], stdout=PIPE, universal_newlines=True)
        result = link(proc.stdout, dst)
        out = dst.get(timeout=TIMEOUT)
        proc.wait()
        self.assertEqual(TEXT, out)
        result.stop()

    def test_file_path_to_queue(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(TEXT)
            fname = f.name
        try:
            dst = queue.Queue()
            result = link(fname, dst)
            out = dst.get(timeout=TIMEOUT)
            self.assertEqual(TEXT, out)
            result.stop()
        finally:
            os.unlink(fname)

    def test_handle_to_queue_reader_set(self):
        dst = queue.Queue()
        proc = Popen(['echo', '-n', TEXT], stdout=PIPE, universal_newlines=True)
        result = link(proc.stdout, dst)
        self.assertIsNotNone(result.reader)
        dst.get(timeout=TIMEOUT)
        proc.wait()
        result.stop()

    def test_handle_fan_out_to_multiple_queues(self):
        dst1 = queue.Queue()
        dst2 = queue.Queue()
        proc = Popen(['echo', '-n', TEXT], stdout=PIPE, universal_newlines=True)
        result = link(proc.stdout, [dst1, dst2])
        out1 = dst1.get(timeout=TIMEOUT)
        out2 = dst2.get(timeout=TIMEOUT)
        proc.wait()
        self.assertEqual(TEXT, out1)
        self.assertEqual(TEXT, out2)
        result.stop()


class LinkQueueToHandleTest(unittest.TestCase):
    """queue → handle/path: should produce a writer adapter."""

    def setUp(self):
        logging.config.fileConfig(fname=_get_log_config(), disable_existing_loggers=False)

    def test_queue_to_file_path(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            fname = f.name
        try:
            src = queue.Queue()
            result = link(src, fname)
            src.put(TEXT)
            # Wait for writer to flush
            deadline = time.monotonic() + TIMEOUT
            while time.monotonic() < deadline:
                if os.path.getsize(fname) > 0:
                    break
                time.sleep(0.05)
            result.stop()
            with open(fname) as fh:
                content = fh.read()
            self.assertEqual(TEXT, content)
        finally:
            os.unlink(fname)

    def test_writer_is_set(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            fname = f.name
        try:
            src = queue.Queue()
            result = link(src, fname)
            self.assertEqual(1, len(result.writers))
            result.stop()
        finally:
            os.unlink(fname)


class LinkHandleToHandleTest(unittest.TestCase):
    """handle/path → handle/path: Reader → internal queue → Writer, no QueueLink."""

    def setUp(self):
        logging.config.fileConfig(fname=_get_log_config(), disable_existing_loggers=False)

    def test_file_to_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as src_f:
            src_f.write(TEXT)
            src_name = src_f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as dst_f:
            dst_name = dst_f.name
        try:
            result = link(src_name, dst_name)
            # Wait for writer to flush
            deadline = time.monotonic() + TIMEOUT
            while time.monotonic() < deadline:
                if os.path.getsize(dst_name) > 0:
                    break
                time.sleep(0.05)
            result.stop()
            with open(dst_name) as fh:
                content = fh.read()
            self.assertEqual(TEXT, content)
            # Should have no QueueLink for simple handle→handle
            self.assertIsNone(result.queue_link)
        finally:
            os.unlink(src_name)
            os.unlink(dst_name)

    def test_internal_queue_created(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as src_f:
            src_f.write(TEXT)
            src_name = src_f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as dst_f:
            dst_name = dst_f.name
        try:
            result = link(src_name, dst_name)
            self.assertEqual(1, len(result._internal_queues))
            result.stop()
        finally:
            os.unlink(src_name)
            os.unlink(dst_name)

    def test_lifecycle_workers_terminate(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as src_f:
            src_f.write(TEXT)
            src_name = src_f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as dst_f:
            dst_name = dst_f.name
        try:
            result = link(src_name, dst_name)
            time.sleep(0.5)
            result.stop()
            deadline = time.monotonic() + 5
            while result.is_alive() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(result.is_alive())
        finally:
            os.unlink(src_name)
            os.unlink(dst_name)


class LinkFanOutMixedTest(unittest.TestCase):
    """handle → [queue, path]: Reader → internal queue → QueueLink → per-dest."""

    def setUp(self):
        logging.config.fileConfig(fname=_get_log_config(), disable_existing_loggers=False)

    def test_handle_to_queue_and_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as src_f:
            src_f.write(TEXT)
            src_name = src_f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as dst_f:
            dst_name = dst_f.name
        try:
            dst_q = queue.Queue()
            result = link(src_name, [dst_q, dst_name])
            # Check queue destination
            out = dst_q.get(timeout=TIMEOUT)
            self.assertEqual(TEXT, out)
            # Check file destination
            deadline = time.monotonic() + TIMEOUT
            while time.monotonic() < deadline:
                if os.path.getsize(dst_name) > 0:
                    break
                time.sleep(0.05)
            result.stop()
            with open(dst_name) as fh:
                content = fh.read()
            self.assertEqual(TEXT, content)
        finally:
            os.unlink(src_name)
            os.unlink(dst_name)


class LinkTypeErrorTest(unittest.TestCase):
    """TypeError and ValueError for unsupported inputs."""

    def setUp(self):
        logging.config.fileConfig(fname=_get_log_config(), disable_existing_loggers=False)

    def test_queuelink_as_source_raises(self):
        ql = QueueLink()
        dst = queue.Queue()
        with self.assertRaises(TypeError):
            link(ql, dst)
        ql.stop()

    def test_queuelink_as_destination_raises(self):
        src = queue.Queue()
        ql = QueueLink()
        with self.assertRaises(TypeError):
            link(src, ql)
        ql.stop()

    def test_link_result_as_source_raises(self):
        src = queue.Queue()
        dst = queue.Queue()
        result = link(src, dst)
        dst2 = queue.Queue()
        with self.assertRaises(TypeError):
            link(result, dst2)
        result.stop()

    def test_unsupported_type_raises(self):
        with self.assertRaises(TypeError):
            link(42, queue.Queue())

    def test_tuple_destination_raises(self):
        src = queue.Queue()
        with self.assertRaises(TypeError):
            link(src, (queue.Queue(), queue.Queue()))

    def test_set_destination_raises(self):
        src = queue.Queue()
        with self.assertRaises(TypeError):
            link(src, {queue.Queue()})

    def test_empty_list_destination_raises(self):
        src = queue.Queue()
        with self.assertRaises(ValueError):
            link(src, [])

    def test_duplicate_destination_raises(self):
        src = queue.Queue()
        dst = queue.Queue()
        with self.assertRaises(ValueError):
            link(src, [dst, dst])

    def test_connection_as_destination_raises(self):
        src = queue.Queue()
        recv_conn, send_conn = multiprocessing.Pipe()
        try:
            with self.assertRaises(TypeError):
                link(src, recv_conn)
        finally:
            recv_conn.close()
            send_conn.close()

    def test_connection_source_to_handle_dest_raises(self):
        recv_conn, send_conn = multiprocessing.Pipe()
        try:
            with self.assertRaises(TypeError):
                link(recv_conn, io.StringIO())
        finally:
            recv_conn.close()
            send_conn.close()

    def test_write_only_handle_as_source_raises(self):
        """A write-only handle lacks readline() and should raise TypeError."""
        dst = queue.Queue()
        handle = io.BytesIO()  # has read but not readline in the right sense
        # Manually remove readline to simulate write-only handle
        class WriteOnly:
            def write(self, data): pass
        with self.assertRaises(TypeError):
            link(WriteOnly(), dst)


class LinkSpawnForkserverRegressionTest(unittest.TestCase):
    """Explicit non-matrix regression tests for spawn/forkserver context issues.

    These run internal-queue paths to catch SemLock/context mismatches.
    """

    def _run_queue_to_queue(self, start_method):
        ctx = multiprocessing.get_context(start_method)
        src = ctx.Queue()
        dst = ctx.Queue()
        result = link(src, dst, start_method=start_method)
        src.put(TEXT)
        out = dst.get(timeout=TIMEOUT)
        result.stop()
        self.assertEqual(TEXT, out)

    def test_queue_to_queue_spawn(self):
        self._run_queue_to_queue('spawn')

    def test_queue_to_queue_forkserver(self):
        self._run_queue_to_queue('forkserver')

    def _run_handle_to_queue(self, start_method):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(TEXT)
            fname = f.name
        try:
            dst = queue.Queue()
            result = link(fname, dst, start_method=start_method)
            out = dst.get(timeout=TIMEOUT)
            result.stop()
            self.assertEqual(TEXT, out)
        finally:
            os.unlink(fname)

    def test_file_to_queue_spawn(self):
        self._run_handle_to_queue('spawn')

    def test_file_to_queue_forkserver(self):
        self._run_handle_to_queue('forkserver')


if __name__ == "__main__":
    unittest.main(verbosity=2)
