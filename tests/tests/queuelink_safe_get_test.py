# -*- coding: utf-8 -*-
"""safe_get() edge cases"""
import multiprocessing
import queue
import threading
import time
import unittest

from queue import Empty
from unittest import mock

from queuelink import safe_get


class SafeGetQueueSimpleQueueTest(unittest.TestCase):
    """FEAT-010 (010-3-6): ``queue.SimpleQueue.get()`` supports ``timeout=`` natively
    (Python 3.7+), so ``safe_get`` must use it directly instead of the polling loop
    only ``multiprocessing.SimpleQueue`` needs.

    The polling branch is the only code path in ``safe_get`` that constructs a
    ``Timer``, so patching ``queuelink.common.Timer`` detects whether it was taken.
    """

    def test_queue_simplequeue_returns_item_without_polling(self):
        q = queue.SimpleQueue()
        q.put('item')

        with mock.patch('queuelink.common.Timer') as polling_timer:
            self.assertEqual('item', safe_get(q, timeout=1))

        polling_timer.assert_not_called()

    def test_queue_simplequeue_timeout_raises_empty_without_polling(self):
        q = queue.SimpleQueue()

        with mock.patch('queuelink.common.Timer') as polling_timer:
            with self.assertRaises(Empty):
                safe_get(q, timeout=0.05)

        polling_timer.assert_not_called()

    def test_queue_simplequeue_wakes_as_soon_as_item_arrives(self):
        """A blocked get returns when the item arrives, not at the timeout."""
        q = queue.SimpleQueue()

        putter = threading.Timer(0.1, q.put, args=('late item',))
        putter.start()

        start = time.monotonic()
        self.assertEqual('late item', safe_get(q, timeout=10))
        elapsed = time.monotonic() - start
        putter.join()

        self.assertLess(elapsed, 5, 'safe_get waited for the timeout, not the item')

    def test_multiprocessing_simplequeue_uses_polling(self):
        """Contrast case: multiprocessing.SimpleQueue.get() has no timeout=, so it
        takes the polling path. Confirms the patch target above detects polling."""
        q = multiprocessing.get_context('fork').SimpleQueue()

        with mock.patch('queuelink.common.Timer') as polling_timer:
            polling_timer.return_value.interval.return_value = True  # expire at once
            with self.assertRaises(Empty):
                safe_get(q, timeout=0.05)

        polling_timer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
