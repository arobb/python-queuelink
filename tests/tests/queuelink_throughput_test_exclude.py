# -*- coding: utf-8 -*-
"""tox [-e py313] -- [-n 0] [--verbose] tests/tests/queuelink_throughput_test.py"""
import itertools
import logging
import unittest

from datetime import datetime, tzinfo
from parameterized import parameterized_class

from tests.tests import context
from queuelink.common import PROC_START_METHODS, QUEUE_TYPE_LIST
from queuelink.common import new_id
from queuelink.throughput import Throughput_QueueLink

# # Queue type list for source and destination, plus start methods
# CARTESIAN_SRC_DEST_START_LIST = [(('manager', 'Queue', None), ('manager', 'Queue', None), 'spawn')]
CARTESIAN_SRC_DEST_START_LIST = itertools.product(QUEUE_TYPE_LIST,
                                                  QUEUE_TYPE_LIST,
                                                  PROC_START_METHODS,
                                                  [1,2,3,4,5])  # 5 rounds per test

session_id = new_id()
session_time = datetime.now()

@parameterized_class(('source', 'dest', 'start_method', 'index'), CARTESIAN_SRC_DEST_START_LIST)
class QueueLinkThroughputTestCase(unittest.TestCase):
    def setUp(self):
        self.source_info = {'module': self.source[0],
                            'class': self.source[1],
                            'max_size': self.source[2]}
        self.dest_info = {'module': self.dest[0],
                          'class': self.dest[1],
                          'max_size': self.dest[2]}

    def tearDown(self):
        pass

    def throughput_queuelink_factory(self):
        return Throughput_QueueLink(
            start_method=self.start_method,
            source_type=(self.source_info['module'], self.source_info['class']),
            dest_type=(self.dest_info['module'], self.dest_info['class']),
            session_id=session_id,
            session_time=session_time
        )

    def test_run_throughput(self):
        # t = Throughput_QueueLink('spawn', ('queue', 'Queue'), ('queue', 'Queue'))
        t = self.throughput_queuelink_factory()
        t.time_to_first_element()
        t.stop()

    def test_run_avg_throughput(self):
        t = self.throughput_queuelink_factory()
        t.avg_time_per_element_after_first_queuelink()
        t.stop()

    def test_elements_per_second_throughput(self):
        t = self.throughput_queuelink_factory()
        t.elements_per_second_queuelink()
        t.stop()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkThroughputTestCase)
    unittest.TextTestRunner(verbosity=2).run(suite)
