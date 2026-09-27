"""Measure throughput of QueueLink and the adapters

For each of the concurrency types (threading, fork, forkserver, spawn):
Time to first element
Elements per second
Element transit latency
"""
import itertools
import logging
import multiprocessing
import os
import queue
import statistics
import subprocess
import tempfile
import time

from datetime import datetime
from queue import Empty
from threading import Thread  # For non-multi-processing queues
from typing import Union

from queuelink import QueueLink, DIRECTION, safe_get
from queuelink import QueueHandleAdapterReader, QueueHandleAdapterWriter
from queuelink.timer import Timer
from queuelink.common import PROC_START_METHODS, QUEUE_TYPE_LIST, UNION_SUPPORTED_QUEUES, is_threaded
from throughput_results import ThroughputResults

# Queue type list plus start methods
CARTESIAN_QUEUE_TYPES_START_LIST = itertools.product(QUEUE_TYPE_LIST,
                                                     PROC_START_METHODS)


def send_elements(src_q: UNION_SUPPORTED_QUEUES, text: str, element_count: int):
    """Add an arbitrary amount of data to a queue.

    Intended to run in a separate thread or process.

    Args:
        src_q: Queue to put elements into.
        text: Text string to enqueue.
        element_count: Number of elements to send.
    """
    for i in range(element_count):
        src_q.put(text)


class ConcurrentContext(object):
    """Handle concurrency objects."""
    def __init__(self, start_method: str = None):
        """Initialize a concurrency context.

        Args:
            start_method: Multiprocessing start method. If None, no multiprocessing context
                is created (thread-only mode).
        """
        self.start_method = start_method
        self.manager = None

        if self.start_method:
            self.multiprocessing_ctx = multiprocessing.get_context(self.start_method)
        else:
            self.multiprocessing_ctx = None

    def start_manager(self):
        """Start a multiprocessing manager if one is in use."""
        if not self.start_method:
            raise AttributeError('Cannot use a manager without a start method')

        if not self.manager:
            self.manager = self.multiprocessing_ctx.Manager()

    def stop(self):
        """Stop a multiprocessing manager if one is in use."""
        if hasattr(self.manager, 'shutdown'):
            self.manager.shutdown()

    def Process(self, *args, **kwargs):  # pylint: disable=invalid-name
        """Create a context-appropriate Process."""
        return self.multiprocessing_ctx.Process(*args, **kwargs)

    def parallel_factory(self, source_q: UNION_SUPPORTED_QUEUES) -> Union[Thread, object]:
        """Retrieve the appropriate Thread or Process class for parallel execution.

        Args:
            source_q: Queue instance used to determine threading vs process mode.

        Returns:
            Thread class or context-bound Process class.
        """
        threaded = is_threaded(source_q)

        # Decide whether to use a local thread or process-based publisher
        Parallel = Thread if threaded else self.Process

        return Parallel

    def queue_factory(self, module: str, class_name: str):
        """Return a queue from the given module and class.

        Args:
            module: One of 'queue', 'multiprocessing', or 'manager'.
            class_name: Queue class name within the module.

        Returns:
            A queue instance of the requested type.
        """
        if module == 'queue':
            return getattr(queue, class_name)()

        if module == 'multiprocessing':
            return getattr(self.multiprocessing_ctx, class_name)()

        if module == 'manager':
            self.start_manager()
            return getattr(self.manager, class_name)()


class Throughput(object):
    """Abstract base class for throughput benchmark classes."""
    def __init__(self, start_method: str):
        """Initialize common throughput state.

        Args:
            start_method: Multiprocessing start method (fork, forkserver, spawn).
        """
        self.timeout = 60  # Some spawn instances needed a little more time
        self.text = 'a😂' * 10
        self.logger_name = f'queuelink.throughput.{start_method}'
        self.log = logging.getLogger(self.logger_name)

        # Where to find sample commands (in benchmarks/content/ alongside this file)
        content_dir = os.path.join(os.path.dirname(__file__), 'content')
        sample_command_path = os.path.join(content_dir, 'line_output.py')
        self.sample_command_path = sample_command_path

        self.start_method = start_method
        self.ctx = ConcurrentContext(start_method=start_method)

    def stop(self):
        """Stop the internal multiprocessing manager."""
        self.ctx.stop()

    def queue_factory(self, *args, **kwargs):
        """Delegate queue creation to the concurrency context."""
        return self.ctx.queue_factory(*args, **kwargs)


class Throughput_QueueLink(Throughput):
    """Benchmark QueueLink throughput: time to first element, avg latency, elements per second."""
    def __init__(self, start_method: str, source_type, dest_type,
                 session_id: str = None, session_time: datetime = None,
                 db_path: str = None):
        """Initialize a QueueLink throughput benchmark.

        Args:
            start_method: Multiprocessing start method.
            source_type: Tuple of (module, class_name) for the source queue.
            dest_type: Tuple of (module, class_name) for the destination queue.
            session_id: Session identifier shared across runs.
            session_time: Timestamp for the session.
            db_path: Path to the results SQLite database. Defaults to
                benchmarks/throughput/throughput.sqlite.db.
        """
        super().__init__(start_method=start_method)

        self.source_module = source_type[0]
        self.source_class = source_type[1]
        self.source_path = f'{source_type[0]}.{source_type[1]}'

        self.dest_module = dest_type[0]
        self.dest_class = dest_type[1]
        self.dest_path = f'{dest_type[0]}.{dest_type[1]}'

        # For results reporting
        self.results = ThroughputResults(
            session_id=session_id,
            session_time=session_time,
            start_method=self.start_method,
            source_path=f'{self.source_path}',
            dest_path=f'{self.dest_path}',
            db_path=db_path
        )

    def get_source_q(self):
        """Create and return a new source queue instance."""
        return self.queue_factory(module=self.source_module, class_name=self.source_class)

    def get_dest_q(self):
        """Create and return a new destination queue instance."""
        return self.queue_factory(module=self.dest_module, class_name=self.dest_class)

    def get_from_q(self, target_q):
        """Get one item from target_q with the configured timeout."""
        return safe_get(queue_obj=target_q, timeout=self.timeout)

    def time_to_first_element(self):
        """Measure how long it takes for the first element to be available."""
        source_q = self.get_source_q()
        dest_q = self.get_dest_q()
        queue_link = QueueLink(name='throughput', source=source_q, start_method=self.start_method)

        # Add to the source queue and register
        source_q.put(self.text)

        # Start the timer and register the destination queue (starting the link)
        start = Timer.now()
        queue_link.register_queue(q=dest_q, direction=DIRECTION.TO)

        # Start trying to get the element
        object_out = self.get_from_q(dest_q)
        end = Timer.now()
        timing = round(end - start, 8)

        self.results.put(test_name='time_to_first_element',
                         result=str(timing),
                         result_unit='seconds')

        self.log.info('Time to first element for source %s and destination %s, start method %s: %s',
                      self.source_path, self.dest_path, self.start_method, timing)

    def avg_time_per_element_after_first_queuelink(self):
        """Measure the nominal latency per element after the link has warmed up."""
        iterations = 500
        source_q = self.get_source_q()
        dest_q = self.get_dest_q()
        queue_link = QueueLink(name='avg_throughput', source=source_q, destination=dest_q,
                               start_method=self.start_method)

        # Move the first one through so we only time elements after the link has started
        source_q.put(self.text)
        self.get_from_q(dest_q)

        # Do more
        timing_list = []
        for _ in range(iterations):
            # Place the next item into the source
            source_q.put(self.text)
            start = Timer.now()

            # Start trying to get the element
            object_out = self.get_from_q(dest_q)
            end = Timer.now()
            timing = end - start

            timing_list.append(timing)

        queue_link.close()

        results = {'mean': round(sum(timing_list) / len(timing_list), 8),
                   'median': round(statistics.median(timing_list), 8),
                   'stddev': round(statistics.pstdev(timing_list), 8)}

        self.results.put(test_name='avg_time_per_element_after_first_queuelink',
                         result=results['mean'],
                         result_unit='seconds')

        self.results.put(test_name='median_time_per_element_after_first_queuelink',
                         result=results['median'],
                         result_unit='seconds')

        self.results.put(test_name='stddev_time_per_element_after_first_queuelink',
                         result=results['stddev'],
                         result_unit='seconds')

        self.log.info('Results for time per element across %s elements with source '
                      '%s and destination %s, start method %s: %s',
                      iterations, self.source_path, self.dest_path, self.start_method, results)

    def elements_per_second_queuelink(self):
        """Measure the number of elements per second, baseline vs. through QueueLink."""
        test_q = self.get_source_q()
        source_q = self.get_source_q()
        dest_q = self.get_dest_q()
        queue_link = QueueLink(name='avg_throughput',
                               source=source_q,
                               destination=dest_q,
                               start_method=self.start_method)

        def elements_per_second(element_count, src_q, dst_q):
            """Measure elements passing through in the first second."""
            Parallel = self.ctx.parallel_factory(src_q)
            source_proc = Parallel(
                target=send_elements,
                name='element_source',
                kwargs={
                    'src_q': src_q,
                    'text': self.text,
                    'element_count': element_count})
            source_proc.daemon = True

            # Pull them out
            source_proc.start()
            timer = Timer()
            ts_list = []
            for i in range(element_count):  # Iterate the number of elements
                while True:  # Need to get one and one only element per cycle of the for loop
                    try:
                        self.get_from_q(dst_q)
                        ts_list.append(timer.now())
                        break  # Break the while loop

                    except Empty:
                        continue  # Continue the while loop until we have this one element

            # Join/cleanup the source process
            source_proc.join()

            # Start and end
            start = ts_list[0]
            end = ts_list[-1]

            # Check if the test ended in less than 1 second
            if end - start < 1:
                self.log.debug('Elements/second test for source %s and destination '
                               '%s ended with %i in %f s',
                               self.source_path, self.dest_path, element_count, end - start)
                raise ValueError

            # Find which item index crossed the 1 second mark
            for i, timestamp in enumerate(ts_list):
                if timestamp - start >= 1:
                    return i+1

            raise AssertionError('Looks like we did not exceed 1 second in runtime.')

        def elements_per_seconds_increase(src_q, dst_q):
            """Increase element count until a valid measurement can be taken."""
            element_count = 1000

            while True:
                try:
                    self.log.debug('Elements in per second increase with source %s and '
                                   'destination %s: %i',
                                   self.source_path, self.dest_path, element_count)
                    eps = elements_per_second(element_count=element_count, src_q=src_q, dst_q=dst_q)
                    return eps

                except ValueError:
                    element_count *= 10

        try:
            # Baseline read rate from a queue
            baseline_eps = elements_per_seconds_increase(src_q=test_q, dst_q=test_q)

            self.results.put(test_name='elements_per_second_queuelink_baseline',
                             result=str(baseline_eps),
                             result_unit='elements_per_second')

            # Actual rate from the link
            actual_eps = elements_per_seconds_increase(src_q=source_q, dst_q=dest_q)

            self.results.put(test_name='elements_per_second_queuelink_actual',
                             result=str(actual_eps),
                             result_unit='elements_per_second')

            self.log.info('Elements per second with baseline (added/removed from one queue) '
                          'on %s: %i, and actual (two queues connected by a QueueLink) based on '
                          'source %s and destination %s: %i',
                          self.source_path, baseline_eps, self.source_path,
                          self.dest_path, actual_eps)
        finally:
            queue_link.close()


class Throughput_QueueHandleAdapterReader(Throughput):
    """Benchmark QueueHandleAdapterReader throughput: time to first line, lines per second."""

    def __init__(self, start_method: str, source_type,
                 session_id: str = None, session_time: datetime = None,
                 db_path: str = None):
        """Initialize a QueueHandleAdapterReader throughput benchmark.

        Args:
            start_method: Multiprocessing start method.
            source_type: Tuple of (module, class_name) for the destination queue.
            session_id: Session identifier shared across runs.
            session_time: Timestamp for the session.
            db_path: Path to the results SQLite database. Defaults to
                benchmarks/throughput/throughput.sqlite.db.
        """
        super().__init__(start_method=start_method)
        self.source_module = source_type[0]
        self.source_class = source_type[1]
        self.source_path = f'{source_type[0]}.{source_type[1]}'
        self.results = ThroughputResults(
            session_id=session_id,
            session_time=session_time,
            start_method=self.start_method,
            source_path='subprocess.stdout',
            dest_path=self.source_path,
            db_path=db_path)

    def time_to_first_line(self):
        """Measure time from adapter start until first line arrives in the queue."""
        dest_q = self.queue_factory(module=self.source_module, class_name=self.source_class)
        proc = subprocess.Popen(
            ['python', self.sample_command_path, '-l', '1'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        start = Timer.now()
        adapter = QueueHandleAdapterReader(
            queue=dest_q,
            handle=proc.stdout,
            start_method=self.start_method)
        adapter.start()

        item = safe_get(dest_q, timeout=self.timeout)
        end = Timer.now()
        timing = round(end - start, 8)

        adapter.stop()
        proc.wait()

        self.results.put(test_name='reader_time_to_first_line',
                         result=str(timing),
                         result_unit='seconds')
        self.log.info('Reader time_to_first_line for %s start method %s: %s',
                      self.source_path, self.start_method, timing)

    def lines_per_second(self, line_count: int = 1000):
        """Measure lines per second from subprocess stdout through the adapter into a queue.

        Args:
            line_count: Number of lines to send through the adapter.
        """
        dest_q = self.queue_factory(module=self.source_module, class_name=self.source_class)
        proc = subprocess.Popen(
            ['python', self.sample_command_path, '-l', str(line_count)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        adapter = QueueHandleAdapterReader(
            queue=dest_q,
            handle=proc.stdout,
            start_method=self.start_method)
        adapter.start()

        timer = Timer()
        ts_list = []
        for _ in range(line_count):
            safe_get(dest_q, timeout=self.timeout)
            ts_list.append(timer.now())

        adapter.stop()
        proc.wait()

        if len(ts_list) >= 2:
            elapsed = ts_list[-1] - ts_list[0]
            lps = round(len(ts_list) / elapsed, 2) if elapsed > 0 else 0.0
        else:
            lps = 0.0

        self.results.put(test_name='reader_lines_per_second',
                         result=str(lps),
                         result_unit='lines_per_second')
        self.log.info('Reader lines_per_second for %s start method %s: %s',
                      self.source_path, self.start_method, lps)


class Throughput_QueueHandleAdapterWriter(Throughput):
    """Benchmark QueueHandleAdapterWriter throughput: lines per second from queue to file."""

    def __init__(self, start_method: str, source_type,
                 session_id: str = None, session_time: datetime = None,
                 db_path: str = None):
        """Initialize a QueueHandleAdapterWriter throughput benchmark.

        Args:
            start_method: Multiprocessing start method.
            source_type: Tuple of (module, class_name) for the source queue.
            session_id: Session identifier shared across runs.
            session_time: Timestamp for the session.
            db_path: Path to the results SQLite database. Defaults to
                benchmarks/throughput/throughput.sqlite.db.
        """
        super().__init__(start_method=start_method)
        self.source_module = source_type[0]
        self.source_class = source_type[1]
        self.source_path = f'{source_type[0]}.{source_type[1]}'
        self.results = ThroughputResults(
            session_id=session_id,
            session_time=session_time,
            start_method=self.start_method,
            source_path=self.source_path,
            dest_path='tempfile',
            db_path=db_path)

    def lines_per_second(self, line_count: int = 1000):
        """Measure lines per second from queue through the adapter to a temp file.

        Args:
            line_count: Number of lines to write through the adapter.
        """
        src_q = self.queue_factory(module=self.source_module, class_name=self.source_class)

        # Pre-fill the queue
        for i in range(line_count):
            src_q.put(f'Line {i}\n')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            tmp_path = tmp.name

        try:
            adapter = QueueHandleAdapterWriter(
                queue=src_q,
                handle=tmp_path,
                start_method=self.start_method)
            adapter.start()

            # Wait until all lines are written
            start = Timer.now()
            deadline = start + self.timeout
            while True:
                try:
                    count = sum(1 for _ in open(tmp_path))  # pylint: disable=unspecified-encoding
                except OSError:
                    count = 0
                if count >= line_count or Timer.now() > deadline:
                    break
                time.sleep(0.01)

            end = Timer.now()
            elapsed = end - start
            lps = round(line_count / elapsed, 2) if elapsed > 0 else 0.0

            adapter.stop()
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        self.results.put(test_name='writer_lines_per_second',
                         result=str(lps),
                         result_unit='lines_per_second')
        self.log.info('Writer lines_per_second for %s start method %s: %s',
                      self.source_path, self.start_method, lps)
