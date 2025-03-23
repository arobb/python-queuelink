# -*- coding: utf-8 -*-
import logging
import multiprocessing
import os
import unittest

from itertools import product
from subprocess import Popen, PIPE

from parameterized import parameterized, parameterized_class

from tests.tests import context
from queue import Queue
from queuelink import QueueLink
from queuelink import QueueHandleAdapterReader
from queuelink.common import PROC_START_METHODS


@parameterized_class(('start_method'), product(PROC_START_METHODS))
class QueueLinkExampleTestCase(unittest.TestCase):
    def setUp(self):
        content_dir = os.path.join(os.path.dirname(__file__), '..', 'content')

        log_config_fname = os.path.join(content_dir, 'testing_logging_config.ini')
        logging.config.fileConfig(fname=log_config_fname, disable_existing_loggers=False)

    def test_example_threaded(self):
        # Source and destination queues
        source_q = Queue()
        dest_q = Queue()

        # Create the QueueLink
        queue_link = QueueLink(name="my link", start_method=self.start_method)

        # Connect queues to the QueueLink
        source_id = queue_link.read(queue_proxy=source_q)
        dest_id = queue_link.write(queue_proxy=dest_q)

        # Text to send
        text_in = "a😂" * 10

        # Add text to the source queue
        source_q.put(text_in)

        # Retrieve the text from the destination queue!
        text_out = dest_q.get(timeout=1)
        self.assertEqual(text_in, text_out, 'Text is inconsistent')

    def test_cross_thread_multiprocess(self):
        # Source and destination
        source_q = Queue()  # Thread-based
        dest_q = multiprocessing.get_context(self.start_method).Queue()  # Process-based

        # Create the QueueLink
        queue_link = QueueLink(name="my link", start_method=self.start_method)

        # Connect queues to the QueueLink
        source_id = queue_link.read(queue_proxy=source_q)
        dest_id = queue_link.write(queue_proxy=dest_q)

        # Text to send
        text_in = "a😂" * 10

        # Add text to the source queue
        source_q.put(text_in)

        # Retrieve the text from the destination queue!
        text_out = dest_q.get(timeout=1)
        self.assertEqual(text_in, text_out, 'Text is inconsistent')

    def test_cross_thread_managed_multiprocess(self):
        # Process manager
        manager = multiprocessing.get_context(self.start_method).Manager()

        # Source and destination
        source_q = Queue()  # Thread-based
        dest_q = manager.Queue()  # Process-based

        # Create the QueueLink
        queue_link = QueueLink(name="my link", start_method=self.start_method)

        # Connect queues to the QueueLink
        source_id = queue_link.read(queue_proxy=source_q)
        dest_id = queue_link.write(queue_proxy=dest_q)

        # Text to send
        text_in = "a😂" * 10

        # Add text to the source queue
        source_q.put(text_in)

        # Retrieve the text from the destination queue!
        text_out = dest_q.get(timeout=1)
        manager.shutdown()
        self.assertEqual(text_in, text_out, 'Text is inconsistent')

    def test_reader(self):
        # Text to send
        text_in = "a😂" * 10

        # Destination queue
        dest_q = multiprocessing.get_context(self.start_method).Queue()  # Process-based

        # Subprocess, simple example sending some text to stdout
        # from subprocess import Popen, PIPE
        proc = Popen(['echo', '-n', text_in],  # -n prevents echo from adding a newline character
                     stdout=PIPE,
                     universal_newlines=True,
                     close_fds=True)

        # Connect the reader
        # from queuelink import QueueHandleAdapterReader
        read_adapter = QueueHandleAdapterReader(queue=dest_q,
                                                handle=proc.stdout,
                                                start_method=self.start_method)

        # Get the text from the queue
        text_out = dest_q.get()
        self.assertEqual(text_in, text_out, 'Text is inconsistent')


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkExampleTestCase)
    unittest.TextTestRunner(verbosity=2).run(suite)
