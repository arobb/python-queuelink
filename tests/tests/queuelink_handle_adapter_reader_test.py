# -*- coding: utf-8 -*-
import codecs
import itertools
import logging
import multiprocessing
import queue
import os
import subprocess
import unittest

from queue import Empty
from parameterized import parameterized
from parameterized import parameterized_class
from subprocess import PIPE

from tests.tests import context
from queuelink.common import PROC_START_METHODS, QUEUE_TYPE_LIST
from queuelink import QueueLink
from queuelink import QueueHandleAdapterReader

# Queue type list plus start methods
CARTESIAN_QUEUE_TYPES_START_LIST = itertools.product(QUEUE_TYPE_LIST,
                                                  PROC_START_METHODS)

# TODO: Add N-round tests to check for performance issues with multiple items flowing through

@parameterized_class(('queue_type', 'start_method'), CARTESIAN_QUEUE_TYPES_START_LIST)
class QueueLinkHandleAdapterReaderTestCase(unittest.TestCase):
    def setUp(self):
        self.timeout = 60  # Some spawn instances needed a little more time

        content_dir = os.path.join(os.path.dirname(__file__), '..', 'content')

        log_config_fname = os.path.join(content_dir, 'testing_logging_config.ini')
        logging.config.fileConfig(fname=log_config_fname, disable_existing_loggers=False)

        sampleCommandPath = os.path.join(content_dir, 'line_output.py')
        self.sampleCommandPath = sampleCommandPath

        # Queue info and start method
        self.queue_module = self.queue_type[0]
        self.queue_class = self.queue_type[1]
        self.queue_max = self.queue_type[2]
        self.queue_class_path = f'{self.queue_module}.{self.queue_class}'

        # Context and Manager if needed
        self.multiprocessing_ctx = multiprocessing.get_context(self.start_method)
        self.manager = self.multiprocessing_ctx.Manager()

    def tearDown(self):
        self.manager.shutdown()

    def queue_factory(self):
        if self.queue_module == 'queue':
            return getattr(queue, self.queue_class)()

        if self.queue_module == 'multiprocessing':
            return getattr(self.multiprocessing_ctx, self.queue_class)()

        if self.queue_module == 'manager':
            return getattr(self.manager, self.queue_class)()

    # def source_destination_movement_subprocess_pipe(self, rounds: int=1):
    #     """Reusable source-destination method"""
    #     # Text in
    #     text_in = 'a😂' * 10
    #
    #     # Subprocess
    #     proc = subprocess.Popen([self.sampleCommandPath,
    #                              '--manual', text_in,
    #                              '--lines', str(rounds)],
    #                             stdout=PIPE, universal_newlines=newlines, close_fds=True)
    #
    #     # Destination queues
    #     dest_q = self.queue_factory()
    #
    #     # Connect the reader
    #     read_adapter = QueueHandleAdapterReader(dest_q, handle=proc.stdout,
    #                                             start_method=self.start_method)


    @parameterized.expand([
        [False],
        [True]
    ])
    def test_read_subprocess_pipe(self, newlines):
        # Text in
        text_in = 'a😂' * 10

        # Subprocess
        proc = subprocess.Popen([self.sampleCommandPath, '--manual', text_in, '--lines', '1'],
                                stdout=PIPE, universal_newlines=newlines, close_fds=True)

        # Destination queues
        dest_q = self.queue_factory()

        # Connect the reader
        read_adapter = QueueHandleAdapterReader(dest_q, handle=proc.stdout,
                                                start_method=self.start_method)

        # Retrieve the text from the destination queue
        try:
            wrapper = QueueLink._queue_get_with_timeout(queue_proxy=dest_q,
                                                        timeout=self.timeout)

            # Mark we pulled it for JoinableQueues
            if hasattr(dest_q, 'task_done'):
                dest_q.task_done()

        except Empty:
            link_alive = read_adapter.is_alive()

            raise Empty('Destination queue is empty because the publisher process '
                        f'has died for {self.queue_class_path}, '
                        f'and start method {self.start_method}.')

        # If newlines is false the value will be a bytes
        out_value = wrapper.value
        text_out = out_value.strip('\n') if newlines else out_value.decode('utf8').strip('\n')
        self.assertEqual(text_in, text_out, 'Text is inconsistent')

    @parameterized.expand([
        [False],
        [True]
    ])
    def test_read_multiprocess_connection(self, trusted):
        # Text in
        text_in = 'a😂' * 10

        # Subprocess
        c1, c2 = multiprocessing.Pipe()

        # Destination queue
        dest_q = self.queue_factory()

        # Connect the reader
        read_adapter = QueueHandleAdapterReader(dest_q,
                                                handle=c2,
                                                start_method=self.start_method,
                                                trusted=trusted)

        # Send the text to the pipe (first connection)
        if trusted:
            c1.send(text_in)
        else:
            c1.send_bytes(text_in.encode('utf8'))

        # Pull the value
        try:
            wrapper = QueueLink._queue_get_with_timeout(queue_proxy=dest_q,
                                                        timeout=self.timeout)

            # Mark we pulled it for JoinableQueues
            if hasattr(dest_q, 'task_done'):
                dest_q.task_done()

        except Empty:
            link_alive = read_adapter.is_alive()

            raise Empty('Destination queue is empty because the publisher process '
                        f'has died for {self.queue_class_path}, start method {self.start_method}, '
                        f'and {"trusted" if trusted else "untrusted"} Connections.')

        # If newlines is false the value will be a bytes
        if trusted:
            text_out = wrapper
        else:
            text_out = str(wrapper)
        self.assertEqual(text_in, text_out, 'Text is inconsistent')


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkHandleAdapterReaderTestCase)
    unittest.TextTestRunner(verbosity=2).run(suite)