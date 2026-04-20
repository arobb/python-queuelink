# -*- coding: utf-8 -*-
"""tox [-e py313] -- [-n 0] [--verbose] benchmarks/throughput_test_exclude.py"""
import itertools
import logging
import unittest

from datetime import datetime, tzinfo
from parameterized import parameterized_class

import context  # noqa: F401 - imported for sys.path side-effect
from queuelink.common import PROC_START_METHODS, QUEUE_TYPE_LIST
from queuelink.common import new_id
from throughput import Throughput_QueueLink
from throughput import Throughput_QueueHandleAdapterReader, Throughput_QueueHandleAdapterWriter

# # Queue type list for source and destination, plus start methods
# CARTESIAN_SRC_DEST_START_LIST = [(('manager', 'Queue', None), ('manager', 'Queue', None), 'spawn')]
CARTESIAN_SRC_DEST_START_LIST = itertools.product(QUEUE_TYPE_LIST,
                                                  QUEUE_TYPE_LIST,
                                                  PROC_START_METHODS,
                                                  [1, 2, 3, 4, 5])  # 5 rounds per test

session_id = new_id()
session_time = datetime.now()

@parameterized_class(('source', 'dest', 'start_method', 'index'), CARTESIAN_SRC_DEST_START_LIST)
class QueueLinkThroughputTestCase(unittest.TestCase):
    """Parameterized QueueLink throughput tests across all queue type pairs and start methods."""
    def setUp(self):
        """Set up source and destination queue info from parameterized values."""
        self.source_info = {'module': self.source[0],
                            'class': self.source[1],
                            'max_size': self.source[2]}
        self.dest_info = {'module': self.dest[0],
                          'class': self.dest[1],
                          'max_size': self.dest[2]}

    def tearDown(self):
        """Tear down after each test."""

    def throughput_queuelink_factory(self):
        """Create a Throughput_QueueLink instance with session-level IDs."""
        return Throughput_QueueLink(
            start_method=self.start_method,
            source_type=(self.source_info['module'], self.source_info['class']),
            dest_type=(self.dest_info['module'], self.dest_info['class']),
            session_id=session_id,
            session_time=session_time
        )

    def test_run_throughput(self):
        """Measure time to first element."""
        t = self.throughput_queuelink_factory()
        t.time_to_first_element()
        t.stop()

    def test_run_avg_throughput(self):
        """Measure average time per element after warmup."""
        t = self.throughput_queuelink_factory()
        t.avg_time_per_element_after_first_queuelink()
        t.stop()

    def test_elements_per_second_throughput(self):
        """Measure elements per second baseline and through QueueLink."""
        t = self.throughput_queuelink_factory()
        t.elements_per_second_queuelink()
        t.stop()


CARTESIAN_ADAPTER_SRC_START_LIST = itertools.product(QUEUE_TYPE_LIST,
                                                     PROC_START_METHODS,
                                                     [1, 2, 3, 4, 5])


@parameterized_class(('source', 'start_method', 'index'), CARTESIAN_ADAPTER_SRC_START_LIST)
class QueueHandleAdapterReaderThroughputTestCase(unittest.TestCase):
    """Parameterized QueueHandleAdapterReader throughput tests across queue types and start methods."""
    def setUp(self):
        """Set up source queue info from parameterized values."""
        self.source_info = {'module': self.source[0], 'class': self.source[1]}

    def throughput_factory(self):
        """Create a Throughput_QueueHandleAdapterReader instance with session-level IDs."""
        return Throughput_QueueHandleAdapterReader(
            start_method=self.start_method,
            source_type=(self.source_info['module'], self.source_info['class']),
            session_id=session_id,
            session_time=session_time)

    def test_time_to_first_line(self):
        """Measure time from adapter start until first line arrives in the queue."""
        t = self.throughput_factory()
        t.time_to_first_line()
        t.stop()

    def test_lines_per_second(self):
        """Measure lines per second from subprocess stdout through the adapter."""
        t = self.throughput_factory()
        t.lines_per_second()
        t.stop()


@parameterized_class(('source', 'start_method', 'index'), CARTESIAN_ADAPTER_SRC_START_LIST)
class QueueHandleAdapterWriterThroughputTestCase(unittest.TestCase):
    """Parameterized QueueHandleAdapterWriter throughput tests across queue types and start methods."""
    def setUp(self):
        """Set up source queue info from parameterized values."""
        self.source_info = {'module': self.source[0], 'class': self.source[1]}

    def throughput_factory(self):
        """Create a Throughput_QueueHandleAdapterWriter instance with session-level IDs."""
        return Throughput_QueueHandleAdapterWriter(
            start_method=self.start_method,
            source_type=(self.source_info['module'], self.source_info['class']),
            session_id=session_id,
            session_time=session_time)

    def test_lines_per_second(self):
        """Measure lines per second from queue through the adapter to a temp file."""
        t = self.throughput_factory()
        t.lines_per_second()
        t.stop()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkThroughputTestCase)
    unittest.TextTestRunner(verbosity=2).run(suite)
