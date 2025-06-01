# -*- coding: utf-8 -*-
import itertools
import logging
import multiprocessing
import queue
import os
import sys
import tempfile
import time
import unittest

from pathlib import Path

from parameterized import parameterized
from parameterized import parameterized_class

from tests.tests import context
from queuelink.common import PROC_START_METHODS, QUEUE_TYPE_LIST
from queuelink import QueueHandleAdapterWriter
from queuelink import Timer

# Queue type list plus start methods
CARTESIAN_QUEUE_TYPES_START_LIST = itertools.product(QUEUE_TYPE_LIST,
                                                  PROC_START_METHODS,
                                                     [True, False])


@parameterized_class(('queue_type', 'start_method', 'thread_only'),
                     CARTESIAN_QUEUE_TYPES_START_LIST)
class QueueLinkHandleAdapterWriterTestCase(unittest.TestCase):
    def setUp(self):
        if sys.version_info[0] == 3 and sys.version_info[1] == 12:
            self.timeout = 60  # Some instances needed a little more time in 3.12
        else:
            self.timeout = 10

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

    @parameterized.expand(itertools.product(['True', 'False'], ['handle', 'string', 'path']))
    def test_write_handle(self, binary: bool, handle_type: str):
        count = 10
        text_in = 'a😂' * count
        src_queue = self.queue_factory()

        # Name
        name = f'binary_{binary}_handle_type_{handle_type}_thread_only_{self.thread_only}'

        # File open type
        mode = 'w+b' if binary else 'w+'

        with tempfile.NamedTemporaryFile(mode=mode, newline=None) as f:

            # Create the writer object with different types of "handles"
            if handle_type == 'handle':
                writer = QueueHandleAdapterWriter(
                    name=name,
                    queue=src_queue,
                    handle=f,
                    start_method=self.start_method,
                    thread_only=self.thread_only)

            elif handle_type == 'string':
                writer = QueueHandleAdapterWriter(
                    name=name,
                    queue=src_queue,
                    handle=f.name,
                    start_method=self.start_method,
                    thread_only=self.thread_only)

            elif handle_type == 'path':
                temp_path = Path(f.name)
                writer = QueueHandleAdapterWriter(
                    name=name,
                    queue=src_queue,
                    handle=temp_path,
                    start_method=self.start_method,
                    thread_only=self.thread_only)

            # Put content into the queue
            for i in range(count):
                src_queue.put(text_in.encode('utf8') if binary else text_in)

            # Wait until the writer is done processing messsages
            logging_timer = Timer(interval=0.25)
            timeout_timer = Timer(interval=self.timeout)
            while writer.get_messages_processed() < count:
                processed_count = writer.get_messages_processed()

                if logging_timer.interval():
                    logging.info(f"Not done yet: processed {processed_count} of {count}")

                if not writer.is_alive():
                    logging.error(f'Writer process has died')
                    break

                if timeout_timer.interval():
                    writer.close()
                    logging.error(f'Writer test timed out: processed {processed_count} of {count}')
                    self.fail(f'Writer test timed out: processed {processed_count} of {count}')

                time.sleep(.001)

            # Stop the writer
            writer.close()

            # Read the content from the temp file
            f.seek(0)
            content_out = f.read()
            content_compare = text_in * count
            content_compare = content_compare.encode('utf8') if binary else content_compare
            self.assertEqual(content_compare,
                             content_out,
                             f'Not equal: {content_compare}, {content_out}')


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkHandleAdapterWriterTestCase)
    unittest.TextTestRunner(verbosity=2).run(suite)
