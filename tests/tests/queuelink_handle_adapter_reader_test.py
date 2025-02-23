# -*- coding: utf-8 -*-
import codecs
import itertools
import logging
import multiprocessing
import queue
import os
import subprocess
import unittest

from typing import Union

from queue import Empty
from parameterized import parameterized
from parameterized import parameterized_class
from subprocess import PIPE

from tests.tests import context
from queuelink.common import PROC_START_METHODS, QUEUE_TYPE_LIST
from queuelink import QueueLink
from queuelink import QueueHandleAdapterReader
from queuelink import ContentWrapper, WRAP_WHEN

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

    def subprocess_factory(self, text_in: str=None, newlines: bool=True, line_count: int=1):
        if not text_in:
            text_in = 'a😂' * 10

        proc = subprocess.Popen([self.sampleCommandPath,
                                 '--manual', text_in,
                                 '--lines', str(line_count)],
                                stdout=PIPE,
                                universal_newlines=newlines,
                                close_fds=True)

        return proc

    def movement_subprocess_pipe(self,
                                 wrap_when: WRAP_WHEN,
                                 newlines: bool,
                                 line_count: int=1) -> (Union[str, ContentWrapper], str):
        """Reusable source-destination method for subprocesses"""
        # Text in
        text_in = 'a😂' * 10

        # Subprocess
        proc = self.subprocess_factory(text_in=text_in, newlines=newlines, line_count=line_count)

        # Destination queues
        dest_q = self.queue_factory()

        # Connect the reader
        read_adapter = QueueHandleAdapterReader(dest_q, handle=proc.stdout,
                                                start_method=self.start_method,
                                                wrap_when=wrap_when)

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

        finally:
            read_adapter.close()

        return text_in, wrapper

    def movement_multiprocess_conn(self,
                                   wrap_when: WRAP_WHEN,
                                   trusted: bool=True,
                                   text_len: int=10) -> (Union[str, ContentWrapper], str):
        """Reusable source-destination method for multiprocess connections"""
        # Text in
        faces = '😂' * text_len
        text_in = faces if text_len == 1 else f'a{faces[:-1]}'  # include leading 'a'

        # Subprocess
        c1, c2 = multiprocessing.Pipe()

        # Destination queue
        dest_q = self.queue_factory()

        # Connect the reader
        read_adapter = QueueHandleAdapterReader(dest_q,
                                                handle=c2,
                                                start_method=self.start_method,
                                                trusted=trusted,
                                                wrap_when=wrap_when)

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

        finally:
            for conn in [c1, c1]:
                try:
                    c1.close()
                    c2.close()

                except OSError as e:
                    # Bad file descriptor / handle is closed
                    if e.errno != 9:
                        raise e

        return text_in, wrapper

    @parameterized.expand(itertools.product([True, False], WRAP_WHEN))
    def test_read_subprocess_pipe(self, newlines, wrap_when):
        text_in, wrapper = self.movement_subprocess_pipe(wrap_when=wrap_when, newlines=newlines)

        # If newlines is false the value will be a bytes
        out_value = wrapper.value if isinstance(wrapper, ContentWrapper) else wrapper
        text_out = out_value.strip('\n') if newlines else out_value.decode('utf8').strip('\n')
        self.assertEqual(text_in, text_out, 'Text is inconsistent')

    @parameterized.expand(itertools.product([True, False], WRAP_WHEN))
    def test_read_multiprocess_connection(self, trusted, wrap_when):
        text_in, wrapper = self.movement_multiprocess_conn(wrap_when=wrap_when, trusted=trusted)

        # Extract value if wrapped
        text_out = wrapper.value if isinstance(wrapper, ContentWrapper) else wrapper

        # If trusted is false the value will be a bytes
        if not trusted:
            text_out = text_out.decode('utf8')
        self.assertEqual(text_in, text_out, 'Text is inconsistent')

    @parameterized.expand(itertools.product(WRAP_WHEN, [ContentWrapper.THRESHOLD-1,
                                                        ContentWrapper.THRESHOLD,
                                                        ContentWrapper.THRESHOLD+1]))
    def test_wrapping(self, wrap_when, text_len):
        """Verify that wrapping happens when, and only when, it is supposed to"""
        text_in, wrapper = self.movement_multiprocess_conn(wrap_when=wrap_when,
                                                           text_len=text_len)

        # Always
        if wrap_when == WRAP_WHEN.ALWAYS:
            self.assertIsInstance(wrapper, ContentWrapper,
                                  "Wrap is set to Always, but return is not a ContentWrapper")

        # Never
        if wrap_when == WRAP_WHEN.NEVER:
            self.assertNotIsInstance(wrapper, ContentWrapper,
                                     "Wrap is set to Never, but return is a ContentWrapper")

        # Auto
        if wrap_when == WRAP_WHEN.AUTO:
            if text_len < ContentWrapper.THRESHOLD:
                self.assertNotIsInstance(wrapper, ContentWrapper,
                                         "Wrap is set to Auto and text is under threshold, "
                                         "but return is a ContentWrapper")

            elif text_len == ContentWrapper.THRESHOLD:
                self.assertNotIsInstance(wrapper, ContentWrapper,
                                         "Wrap is set to Auto and text is at threshold, "
                                         "but return is a ContentWrapper")

            else:
                self.assertIsInstance(wrapper, ContentWrapper,
                                      f"Wrap is set to Auto, and text is over threshold but "
                                      f"return is not a ContentWrapper")


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkHandleAdapterReaderTestCase)
    unittest.TextTestRunner(verbosity=2).run(suite)