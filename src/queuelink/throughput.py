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

from datetime import datetime
from queue import Empty
from threading import Thread  # For non-multi-processing queues
from typing import Union

from queuelink import QueueLink, DIRECTION, safe_get
from queuelink.metrics import Metrics
from queuelink.timer import Timer
from queuelink.common import PROC_START_METHODS, QUEUE_TYPE_LIST, is_threaded
from queuelink.throughput_results import ThroughputResults

# Queue type list plus start methods
CARTESIAN_QUEUE_TYPES_START_LIST = itertools.product(QUEUE_TYPE_LIST,
                                                  PROC_START_METHODS)


def send_elements(src_q: QUEUE_TYPE_LIST, text: str, element_count: int):
    """Function to add arbitrary amount of data to a queue
    Run in a separate thread/process
    """
    for i in range(element_count):
        src_q.put(text)


class concurrent_context(object):
    """Handle concurrency objects"""
    def __init__(self, start_method: str=None):
        self.start_method = start_method
        self.manager = None

        if self.start_method:
            self.multiprocessing_ctx = multiprocessing.get_context(self.start_method)
        else:
            self.multiprocessing_ctx = None

    def start_manager(self):
        if not self.start_method:
            raise AttributeError('Cannot use a manager without a start method')

        if not self.manager:
            self.manager = self.multiprocessing_ctx.Manager()

    def stop(self):
        if hasattr(self.manager, 'shutdown'):
            self.manager.shutdown()

    def Process(self, *args, **kwargs):  # pylint: disable=invalid-name
        """Create a context-appropriate Process"""
        return self.multiprocessing_ctx.Process(*args, **kwargs)

    def parallel_factory(self, source_q: QUEUE_TYPE_LIST) -> Union[Thread, Process]:
        """Retrieve the appropriate Thread or Process class for parallel execution"""
        threaded = is_threaded(source_q)

        # Decide whether to use a local thread or process-based publisher
        Parallel = Thread if threaded else self.Process

        return Parallel

    def queue_factory(self, module: str, class_name: str):
        if module == 'queue':
            return getattr(queue, class_name)()

        if module == 'multiprocessing':
            return getattr(self.multiprocessing_ctx, class_name)()

        if module == 'manager':
            self.start_manager()
            return getattr(self.manager, class_name)()


class Throughput(object):
    def __init__(self, start_method: str):
        self.timeout = 60  # Some spawn instances needed a little more time
        self.text = 'a😂' * 10
        self.logger_name = f'queuelink.throughput.{start_method}'
        self.log = logging.getLogger(self.logger_name)

        # Where to find sample commands and test logging config
        content_dir = os.path.join(os.path.dirname(__file__), '..', 'content')
        sampleCommandPath = os.path.join(content_dir, 'line_output.py')
        self.sampleCommandPath = sampleCommandPath

        self.start_method = start_method
        self.ctx = concurrent_context(start_method=start_method)

    def stop(self):
        self.ctx.stop()

    def queue_factory(self, *args, **kwargs):
        return self.ctx.queue_factory(*args, **kwargs)


class Throughput_QueueLink(Throughput):
    def __init__(self, start_method: str, source_type, dest_type,
                 session_id: str=None, session_time: datetime=None):
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
            dest_path=f'{self.dest_path}'
        )

    def get_source_q(self):
        return self.queue_factory(module=self.source_module, class_name=self.source_class)

    def get_dest_q(self):
        return self.queue_factory(module=self.dest_module, class_name=self.dest_class)

    def get_from_q(self, target_q):
        return safe_get(queue_obj=target_q, timeout=self.timeout)

    def time_to_first_element(self):
        """Measure how long it takes for the first element to be available"""
        timer = Timer()
        source_q = self.get_source_q()
        dest_q = self.get_dest_q()
        queue_link = QueueLink(name='throughput', source=source_q, start_method=self.start_method)

        # Add to the source queue and register
        source_q.put(self.text)

        # Start the timer and register the destination queue (starting the link)
        start = Timer.now()
        queue_link.register_queue(queue_proxy=dest_q, direction=DIRECTION.TO)

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
        """Measure the nominal latency"""
        iterations = 500
        timer = Timer()
        source_q = self.get_source_q()
        dest_q = self.get_dest_q()
        queue_link = QueueLink(name='avg_throughput', source=source_q, destination=dest_q,
                               start_method=self.start_method)

        # Move the first one through so we only time elements after the link has started
        source_q.put(self.text)
        self.get_from_q(dest_q)

        # Do more
        timing_list = []
        for i in range(iterations):
            # Place the next item into the source
            source_q.put(self.text)
            start = Timer.now()

            # Start trying to get the element
            object_out = self.get_from_q(dest_q)
            end = Timer.now()
            timing = end - start

            timing_list.append(timing)

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
        """Measure the number of elements per second"""
        timer = Timer()
        test_q = self.get_source_q()
        source_q = self.get_source_q()
        dest_q = self.get_dest_q()
        queue_link = QueueLink(name='avg_throughput',
                               source=source_q,
                               destination=dest_q,
                               start_method=self.start_method)

        def elements_per_second(element_count, src_q, dst_q):

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
                while True: # Need to get one and one only element per cycle of the for loop
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
            element_count = 1000

            while True:
                try:
                    self.log.debug('Elements in per second increase with source %s and destination %s: %i',
                                   self.source_path, self.dest_path, element_count)
                    eps = elements_per_second(element_count=element_count, src_q=src_q, dst_q=dst_q)
                    return eps

                except ValueError:
                    element_count *= 10

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

        self.log.info('Elements per second with baseline (added/removed from one queue) on %s: %i, '
                      'and actual (two queues connected by a QueueLink) based on source %s and destination %s: %i',
                      self.source_path, baseline_eps, self.source_path, self.dest_path, actual_eps)
