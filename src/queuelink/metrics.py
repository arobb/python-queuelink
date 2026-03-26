# -*- coding: utf-8 -*-
"""Class to handle metrics for QueueLink

from time import sleep
from queuelink.metrics import Metrics, MetricType

metrics = Metrics()
id = metrics.add_element(MetricType.TIMING, name='')
metrics.start(id)
sleep(1)
metrics.lap(id)
out = metrics.get_all_data()
out == { id: {'name': None, 'data_point_count': 2, 'mean': float, 'median': float, 'stddev': float} }

metrics = Metrics()
id = metrics.add_element(MetricType.COUNTING, name='')
metrics.increment(id)
out = metrics.get_all_data()
out == { id: {'name': None, 'count': 1} }
"""
from __future__ import unicode_literals
from __future__ import annotations

import statistics
from enum import Enum

from .classtemplate import ClassTemplate
from .common import new_id
from .timer import Timer


class MetricType(Enum):
    """Supported metric types"""
    TIMING = 'timing'
    COUNTING = 'counting'


class BaseMetric(ClassTemplate):  # pylint: disable=too-few-public-methods
    """Base class for QueueLink monitoring metrics"""

    def __init__(self, name: str = None, max_points: int = 100):
        self.name = name
        self.max_points = max_points
        self._initialize_logging_with_log_name(__name__)


class CountMetric(BaseMetric):
    """Monitoring metric for counter-based information"""

    def __init__(self, name: str = None):
        super().__init__(name=name)
        self.count = 0

    def increment(self):
        """Add 1 to the internal counter"""
        self.count += 1

    def to_dict(self) -> dict:
        """Serialize this metric to a plain dict"""
        return {
            'name': self.name,
            'count': self.count,
        }


class TimedMetric(BaseMetric):
    """Monitoring metric for timing information"""

    def __init__(self, name: str = None, interval: float = None):
        super().__init__(name=name)
        self.interval = interval
        self.data_points = []
        self.mean = 0.0
        self.median = 0.0
        self.stddev = 0.0

        # Set at various times
        self.timer = None
        self.start_time_epoch = None
        self.last_lap = None

    def start(self):
        """Start timing"""
        kwargs = {} if self.interval is None else {'interval': self.interval}
        self.timer = Timer(**kwargs)
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
        self._update_mean()
        self._update_median()
        self._update_stddev()

    def _update_mean(self):
        """Update the average across the available data points"""
        self.mean = statistics.mean(self.data_points)

    def _update_median(self):
        """Update the median across the available data points"""
        self.median = statistics.median(self.data_points)

    def _update_stddev(self):
        """Update the standard deviation across the available data points"""
        self.stddev = statistics.pstdev(self.data_points)

    def to_dict(self) -> dict:
        """Serialize this metric to a plain dict"""
        return {
            'name': self.name,
            'data_point_count': len(self.data_points),
            'mean': self.mean,
            'median': self.median,
            'stddev': self.stddev,
        }


class Metrics(ClassTemplate):
    """Managing multiple metric instances and retrieving values"""

    def __init__(self,
                 name: str = None,
                 log_name: str = None):
        # Unique ID
        self.id = new_id()

        self.name = name
        self.log_name = log_name
        self._initialize_logging_with_log_name(__name__)

        # Element management
        self.elements = {}

    def add_element(self, metric_type: MetricType, name: str = None) -> str:
        """Add a new metric element

        Args:
            metric_type: MetricType.TIMING or MetricType.COUNTING
            name: Optional human-readable name for this element

        Returns:
            element_id string for all future interactions with this element

        Raises:
            ValueError: if metric_type is not a recognised MetricType
        """
        element_id = new_id()
        while element_id in self.elements:
            element_id = new_id()
            self._log.warning('Element ID collision, retrying: %s', str(element_id))

        if metric_type == MetricType.TIMING:
            m = TimedMetric(name=name)
        elif metric_type == MetricType.COUNTING:
            m = CountMetric(name=name)
        else:
            raise ValueError(f'Unknown metric type "{metric_type}"')

        self.elements[element_id] = {'name': name, 'metrics': m}

        return element_id

    def start(self, element_id: str):
        """Start timing metrics"""
        self.elements[element_id]['metrics'].start()

    def lap(self, element_id: str):
        """Update timing metrics based on a recurring event occurrence"""
        self.elements[element_id]['metrics'].lap()

    def increment(self, element_id: str):
        """Increment a counter metric"""
        self.elements[element_id]['metrics'].increment()

    def get(self, element_id: str) -> BaseMetric:
        """Retrieve a single metric instance"""
        return self.elements[element_id]['metrics']

    def get_data(self, element_id: str) -> dict:
        """Retrieve values related to a metric instance"""
        return self.get(element_id).to_dict()

    def get_all_data(self) -> dict:
        """Retrieve data for all metric instances, keyed by element_id

        Returns:
            dict mapping element_id -> metric data dict
        """
        return {eid: self.get_data(eid) for eid in self.elements}
