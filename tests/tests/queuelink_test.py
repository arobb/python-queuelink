# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
import unittest
import multiprocessing
from multiprocessing import Manager

from parameterized import parameterized, parameterized_class

# Python 2
if sys.version_info[0] == 2:
    import Queue as queue
    from Queue import Empty
else:
    import queue
    from queue import Empty

from tests.tests import context
from queuelink import Timer
from queuelink import QueueLink


def safe_get(queue_proxy: multiprocessing.SimpleQueue, timeout: int):
    """Use the timeout feature of a queue if exists, otherwise make our own"""
    timer = Timer(interval=timeout)

    try:
        return queue_proxy.get(timeout=timeout)

    except TypeError:
        while True:
            # Alternate timer
            if timer.interval():
                raise Empty

            try:
                return queue_proxy.get_nowait()

            # SimpleQueues don't have a get_nowait method/mechanism
            except AttributeError:
                # Try not to get stuck, but can't guarantee that another thread hasn't grabbed one
                if queue_proxy.empty():
                    continue
                else:
                    return queue_proxy.get()

            except Empty:
                continue


@parameterized_class(('q_module', 'q_class', 'maxsize'), [
    ('manager', 'Queue', None),
    ('manager', 'JoinableQueue', None),
    ('multiprocessing', 'Queue', None),
    ('multiprocessing', 'JoinableQueue', None),
    ('multiprocessing', 'SimpleQueue', None),
    ('queue', 'Queue', None),
    ('queue', 'LifoQueue', None),
    ('queue', 'PriorityQueue', None),
    ('queue', 'SimpleQueue', None)
])
class QueueLinkTestCase(unittest.TestCase):
    def setUp(self):
        self.manager = Manager()
        self.timeout = 1

    def queue_factory(self):
        if self.q_module == 'queue':
            return getattr(queue, self.q_class)()

        if self.q_module == 'multiprocessing':
            return getattr(multiprocessing, self.q_class)()

        if self.q_module == 'manager':
            return getattr(self.manager, self.q_class)()

    def test_queuelink_get_client_id(self):
        queue_proxy = self.queue_factory()
        queue_link = QueueLink(name="test_link")
        client_id = queue_link.register_queue(queue_proxy=queue_proxy,
                                              direction="source")

        self.assertIsNotNone(client_id,
                             "register_queue did not return a client ID.")

        # Should be able to cast this to an int
        client_id_int = int(client_id)

        self.assertIsInstance(client_id_int,
                              int,
                              "register_queue did not return an int client ID.")

    def test_queuelink_source_destination_movement(self):
        text_in = "a😂" * 10
        source_q = self.queue_factory()
        dest_q = self.queue_factory()
        queue_link = QueueLink(name="test_link")

        source_id = queue_link.register_queue(queue_proxy=source_q,
                                              direction="source")
        dest_id = queue_link.register_queue(queue_proxy=dest_q,
                                            direction="destination")

        # Modify text to support Priority Queues
        tuple_in = (1, text_in)
        source_q.put(tuple_in if self.q_class == "PriorityQueue" else text_in)

        # Pull the value
        try:
            object_out = QueueLink._queue_get_with_timeout(queue_proxy=dest_q, timeout=self.timeout)
            if self.q_class == "PriorityQueue":
                text_out = object_out[1]
            else:
                text_out = object_out

        except Empty:
            raise Empty('Destination queue indicating empty for queue type '
            f'{self.q_module}.{self.q_class}')

        # Mark we pulled it for JoinableQueues
        if hasattr(dest_q, 'task_done'):
            dest_q.task_done()

        self.assertEqual(text_in,
                         text_out,
                         "Text isn't the same across the link")

    @parameterized.expand([
        ["source"],
        ["destination"]
    ])
    def test_queuelink_prevent_multiple_entries(self, direction):
        """Don't allow a user to add the same proxy to a direction multiple
        times."""
        q = self.queue_factory()
        queue_link = QueueLink(name="test_link")

        # Add the queue once
        queue_link.register_queue(queue_proxy=q,
                                  direction=direction)

        # Should raise an error the next time
        self.assertRaises(ValueError,
                          queue_link.register_queue,
                          queue_proxy=q,
                          direction=direction)

    @parameterized.expand([
        ["source", "destination"],
        ["destination", "source"]
    ])
    def test_queuelink_prevent_cyclic_graph(self,
                                                          start_direction,
                                                          end_direction):
        """Don't allow a user to add the same proxy to a direction multiple
        times."""
        q = self.queue_factory()
        queue_link = QueueLink(name="test_link")

        # Add the queue once
        queue_link.register_queue(queue_proxy=q,
                                  direction=start_direction)

        # Should raise an error the next time
        self.assertRaises(ValueError,
                          queue_link.register_queue,
                          queue_proxy=q,
                          direction=end_direction)


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkTestCase)
    unittest.TextTestRunner(verbosity=2).run(suite)
