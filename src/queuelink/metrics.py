# -*- coding: utf-8 -*-
"""Class to handle metrics for QueueLink

from time import sleep
from metrics import Metrics

metrics = Metrics()
id = metrics.add_element(type='timing', name='')
metrics.start(id)
sleep(1)
metrics.lap(id)
out = metrics.get_all_data()
out{ id: {'name': None, 'data_point_count': 2, 'mean': int, 'median': int, 'stddev': int} }

metrics = Metrics()
id = metrics.add_element(type='counting', name='')
metrics.increment(id)
out = metrics.get_all_data()
out{ id: {'name': None, 'count': 1} }
"""
from __future__ import unicode_literals
from __future__ import annotations

import random
import statistics

from .classtemplate import ClassTemplate
from .timer import Timer


class BaseMetric(ClassTemplate):  # pylint: disable=too-few-public-methods
    """Abstract class for QueueLink monitoring metrics"""
    name = ""
    data_points = []
    max_points = 100

class CountMetric(BaseMetric):
    """Monitoring metric for counter-based information"""
    count = 0

    def __init__(self, name: str=None):
        self.name = name
        self._initialize_logging_with_log_name(__name__)

    def increment(self):
        """Add 1 to the internal counter"""
        self.count += 1

class TimedMetric(BaseMetric):
    """Monitoring metric for timing information"""
    mean = 0.0
    median = 0.0
    stddev = 0.0

    def __init__(self, name: str=None, interval: float=None):
        self.name = name
        self.interval = interval
        self._initialize_logging_with_log_name(__name__)

        # Set at various times
        self.timer = None
        self.start_time_epoch = None
        self.last_lap = None

    def start(self):
        """Start timing"""
        self.timer = Timer(interval=self.interval)
        self.start_time_epoch = self.timer.start_time
        self.last_lap = 0

    def lap(self):
        """Count when an event occurs"""
        seconds_since_start = self.timer.lap()
        seconds_since_last_lap = seconds_since_start - self.last_lap

        self.last_lap = seconds_since_start
        self._update_values(new_value=seconds_since_last_lap)

    def _update_values(self, new_value):
        """Provide new values to this method. Do not increment data_points separately."""
        if len(self.data_points) == self.max_points:
            removed = self.data_points.pop(0)
            self._log.debug('Max value count reached, removed oldest data point "%s"', removed)

        self.data_points.append(new_value)
        self._update_mean(new_value)
        self._update_median()
        self._update_stddev()

    def _update_mean(self, new_value):
        """Update the average across the available data points"""
        intermediate = self.mean * (len(self.data_points) - 1)
        self.mean = (intermediate + new_value) / len(self.data_points)

        return self.mean

    def _update_median(self):
        """Update the median across the available data points"""
        self.median = statistics.median(self.data_points)

    def _update_stddev(self):
        """Update the standard deviation across the available data points"""
        self.stddev = statistics.pstdev(self.data_points)


class Metrics(ClassTemplate):
    """Managing multiple metric instances and retrieving values"""
    def __init__(self,
                 name: str=None,
                 log_name: str=None):
        # Unique ID
        self.id = self.new_id()

        self.name = name
        self.log_name = log_name
        self._initialize_logging_with_log_name(__name__)

        # Element management
        self.elements = {}

    def new_id(self) -> str:
        """Get new 6-digit hexadecimal ID string (0-9, A-F)

        :return str
        """
        return ''.join([random.choice(  # nosec
                '0123456789ABCDEF') for x in range(6)])

    def add_element(self, metric_type: str, name: str = None) -> str:
        """timing or counting"""
        element_id = self.new_id()
        while element_id in self.elements:
            element_id = self.new_id()
            self._log.warning('Element ID: %s', str(element_id))

        if metric_type == 'timing':
            m = TimedMetric(name=name)
        elif metric_type == 'counting':
            m = CountMetric(name=name)
        else:
            raise ValueError(f'Unknown metric type "{metric_type}"')

        self.elements[element_id] = {'name': name,
                                     'metrics': m}

        return element_id

    def start(self, element_id: str):
        """Start timing metrics"""
        self.elements[element_id]['metrics'].start()

    def lap(self, element_id: str):
        """Update timing metrics based on a recurring event occurence"""
        self.elements[element_id]['metrics'].lap()

    def increment(self, element_id: str):
        """Increment a counter metric"""
        self.elements[element_id]['metrics'].increment()

    def get(self, element_id: str) -> BaseMetric:
        """Retrieve a single metric instance"""
        return self.elements[element_id]['metrics']

    def get_data(self, element_id: str) -> dict:
        """Retrieve values related to a metric instance"""
        element = self.get(element_id)
        m = {}

        if isinstance(element, TimedMetric):
            m['name'] = element.name
            m['data_point_count'] = len(element.data_points)

            measures = ['mean', 'median', 'stddev']
            for measure in measures:
                m[measure] = getattr(element, measure)

        if isinstance(element, CountMetric):
            m['name'] = element.name
            m['count'] = element.count

        return m

    def get_all_data(self) -> dict:
        """Retrieve data related to all metric instances

        :returns dict
        """
        data_list = []

        for element_id in self.elements:
            data_list.append(self.get_data(element_id))

        return {k: v for d in data_list for k, v in d.items()}
