# -*- coding: utf-8 -*-
import unittest
from tests.tests import context

from queue import Queue
from queuelink import QueueLink

class QueueLinkExampleTestCase(unittest.TestCase):
    def test_example_1(self):
        # Source and destination queues
        source_q = Queue()
        dest_q = Queue()

        # Create the QueueLink
        queue_link = QueueLink(name="my link")

        # Connect queues to the QueueLink
        source_id = queue_link.register_queue(queue_proxy=source_q,
                                              direction="source")
        dest_id = queue_link.register_queue(queue_proxy=dest_q,
                                            direction="destination")

        # Text to send
        text_in = "a😂" * 10
        tuple_in = (1, text_in)

        # Add text to the source queue
        source_q.put(tuple_in)

        # Retrieve the text from the destination queue!
        priority, text_out = dest_q.get(timeout=1)
        self.assertEqual(text_in, text_out, 'Text is inconsistent')

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkExampleTestCase)
    unittest.TextTestRunner(verbosity=2).run(suite)
