"""Test combined functionality with all adapters combined."""
import itertools
import logging
import multiprocessing
import os
import queue
import sys
import tempfile
import time
import unittest

from io import IOBase
from os import PathLike
from pathlib import Path
from typing import Union, Type

from parameterized import parameterized
from parameterized import parameterized_class

from tests.tests import context
from queuelink import QueueHandleAdapterReader
from queuelink import QueueHandleAdapterWriter
from queuelink import Timer
from queuelink.common import PROC_START_METHODS, QUEUE_TYPE_LIST
from queuelink.contentwrapper import WRAP_WHEN


# Queue type list plus start methods
CARTESIAN_QUEUE_TYPES_START_LIST = itertools.product(QUEUE_TYPE_LIST,
                                                     PROC_START_METHODS)


@parameterized_class(('queue_type', 'start_method'), CARTESIAN_QUEUE_TYPES_START_LIST)
class QueueLinkHandleAdapterReaderTestCase(unittest.TestCase):
    def setUp(self):
        if sys.version_info[0] == 3 and sys.version_info[1] == 12:
            self.timeout = 60  # Some instances needed a little more time in 3.12
        else:
            self.timeout = 10

        content_dir = os.path.join(os.path.dirname(__file__), '..', 'content')

        log_config_fname = os.path.join(content_dir, 'testing_logging_config.ini')
        logging.config.fileConfig(fname=log_config_fname, disable_existing_loggers=False)
        self.log = logging.getLogger(f'{__name__}.{self.queue_type}.{self.start_method}')

        sample_command_path = os.path.join(content_dir, 'line_output.py')
        self.sample_command_path = sample_command_path

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

    @staticmethod
    def file_factory(text_in: str,
                     line_count: int) -> tempfile.NamedTemporaryFile:
        """Create a NamedTemporaryFile file with content and return its handle

        User responsible for closing the handle and deleting the file.

        Args:
            text_in: Text to be included in the NamedTemporaryFile
            line_count: Number of lines to add to the file

        Returns:
            A NamedTemporaryFile file handle
        """

        # Open a temporary file to use
        tmp = tempfile.NamedTemporaryFile(delete=False)
        for _ in range(line_count):
            tmp.write(text_in.encode('utf-8'))

        # Make sure everything is on disk
        tmp.flush()

        # Rewind the pointer
        tmp.seek(0)

        return tmp

    def movement_file(self,
                      text_in: str ='a😂' * 10,
                      line_count: int=10,
                      file_reference_type: Type[Union[str, PathLike, IOBase]]=str,
                      wrap_when: WRAP_WHEN=WRAP_WHEN.AUTO,
                      wrap_threshold: int=None) -> (str, str):
        """Perform the content movement and return the input and output content

        Args:
            text_in: Text to be included in the NamedTemporaryFile
            line_count: Number of lines to add to the file
            file_reference_type: How to pass the file reference to the adapters
            wrap_when: When to use a ContentWrapper
            wrap_threshold: Specific file length to use a ContentWrapper if wrap_when is also
                satisfied
        """
        # Create two temp files
        temp_file_source = self.file_factory(text_in=text_in, line_count=line_count)
        temp_file_dest = self.file_factory(text_in=text_in, line_count=0)

        # Set up the references to pass (string, a Path, or the file handle directly)
        try:
            if file_reference_type == str:
                handle_ref_source = temp_file_source.name
                handle_ref_dest = temp_file_dest.name
            elif file_reference_type == PathLike:
                handle_ref_source = Path(temp_file_source.name)
                handle_ref_dest = Path(temp_file_dest.name)
            else:
                handle_ref_source = temp_file_source
                handle_ref_dest = temp_file_dest

            # Destination queue
            dest_q = self.queue_factory()

            # Connect the reader
            # Reads from the pre-populated source file and writes to the destination queue
            read_adapter = QueueHandleAdapterReader(dest_q,
                                                    handle=handle_ref_source,
                                                    start_method=self.start_method,
                                                    wrap_when=wrap_when,
                                                    wrap_threshold=wrap_threshold)

            # Write out
            # Reads from the destination queue and writes to the destination file
            write_adapter = QueueHandleAdapterWriter(dest_q,
                                                     handle=handle_ref_dest,
                                                     start_method=self.start_method)

            timeout_timer = Timer(interval=self.timeout)
            while True:
                # Exit the waiting loop if the read adapter has stopped
                if read_adapter.get_messages_processed() == write_adapter.get_messages_processed() \
                        and read_adapter.get_messages_processed() > 0:
                    break

                # Keep waiting if the reader and writer haven't processed all the content
                # Timeout if we reached the max allowed time
                if timeout_timer.interval():
                    read_msg_count = read_adapter.get_messages_processed()
                    write_msg_count = write_adapter.get_messages_processed()
                    raise TimeoutError(f'Timeout reached: {timeout_timer.interval_period} seconds; '
                                       f'read messages: {read_msg_count}; '
                                       f'written messages: {write_msg_count}; '
                                       f'reference type: {str(file_reference_type)}')

                time.sleep(0.01)

            # Close the adapters. Closing the writer will force a flush.
            read_adapter.close()
            write_adapter.close()

            # Get content from the files
            temp_file_source.seek(0)
            final_text_in = temp_file_source.read()

            temp_file_dest.flush()
            os.fsync(temp_file_dest.fileno())
            temp_file_dest.close()

            # Read the destination file with a new handle
            with open(temp_file_dest.name, mode='rb') as new_dest_handle:
                text_out = new_dest_handle.read()

            return final_text_in, text_out

        finally:
            temp_file_source.close()

            os.unlink(temp_file_source.name)
            os.unlink(temp_file_dest.name)

    @parameterized.expand(itertools.product([10], [10, 1000], WRAP_WHEN, [None]))
    def test_read_file(self,
                       line_len: int=10,
                       line_count: int=10,
                       wrap_when: WRAP_WHEN=WRAP_WHEN.AUTO,
                       wrap_threshold: int=None):
        text_in: str = '😂' * line_len
        final_text_in, text_out = self.movement_file(text_in=text_in,
                                                     line_count=line_count,
                                                     file_reference_type=IOBase,
                                                     wrap_when=wrap_when,
                                                     wrap_threshold=wrap_threshold)

        self.assertEqual(final_text_in, text_out,
                         f'{self.queue_class_path}.{self.start_method}: Text is inconsistent')