# -*- coding: utf-8 -*-
"""Unit tests for the metrics module.

These are focused unit tests — no queue-type/start-method matrix needed because
metrics classes are pure in-process objects with no multiprocessing dependency.
"""
import time
import unittest

from queuelink.metrics import BaseMetric, CountMetric, MetricType, Metrics, TimedMetric


class TestCountMetricInstanceIsolation(unittest.TestCase):
    """Two CountMetric instances must not share state."""

    def test_count_is_independent(self):
        """Incrementing one CountMetric does not affect another."""
        a = CountMetric(name='a')
        b = CountMetric(name='b')

        a.increment()
        a.increment()

        self.assertEqual(a.count, 2)
        self.assertEqual(b.count, 0)

    def test_name_is_independent(self):
        """Name set on one instance is not visible on another."""
        a = CountMetric(name='alpha')
        b = CountMetric(name='beta')

        self.assertEqual(a.name, 'alpha')
        self.assertEqual(b.name, 'beta')


class TestCountMetricBehavior(unittest.TestCase):
    """CountMetric functional tests."""

    def test_starts_at_zero(self):
        m = CountMetric()
        self.assertEqual(m.count, 0)

    def test_increment_advances_count(self):
        m = CountMetric()
        for i in range(1, 6):
            m.increment()
            self.assertEqual(m.count, i)

    def test_to_dict_keys(self):
        m = CountMetric(name='ops')
        m.increment()
        d = m.to_dict()
        self.assertIn('name', d)
        self.assertIn('count', d)
        self.assertEqual(d['name'], 'ops')
        self.assertEqual(d['count'], 1)

    def test_to_dict_no_extra_keys(self):
        m = CountMetric()
        self.assertEqual(set(m.to_dict().keys()), {'name', 'count'})


class TestTimedMetricInstanceIsolation(unittest.TestCase):
    """Two TimedMetric instances must not share state."""

    def test_data_points_are_independent(self):
        """Bug 1 regression: data_points must not be a shared class attribute."""
        a = TimedMetric(name='a')
        b = TimedMetric(name='b')

        a.start()
        time.sleep(0.01)
        a.lap()

        # a has one data point; b should have none
        self.assertEqual(len(a.data_points), 1)
        self.assertEqual(len(b.data_points), 0)

    def test_many_instances_isolated(self):
        """Creating many instances does not accumulate shared data_points."""
        instances = [TimedMetric(name=f'metric_{i}') for i in range(10)]
        for m in instances:
            m.start()
            time.sleep(0.001)
            m.lap()

        for m in instances:
            self.assertEqual(len(m.data_points), 1,
                             msg=f'{m.name} should have exactly 1 data point')


class TestTimedMetricBehavior(unittest.TestCase):
    """TimedMetric functional tests."""

    def setUp(self):
        self.m = TimedMetric(name='test')
        self.m.start()

    def test_lap_adds_data_point(self):
        time.sleep(0.01)
        self.m.lap()
        self.assertEqual(len(self.m.data_points), 1)

    def test_multiple_laps(self):
        for _ in range(5):
            time.sleep(0.001)
            self.m.lap()
        self.assertEqual(len(self.m.data_points), 5)

    def test_mean_is_positive(self):
        time.sleep(0.01)
        self.m.lap()
        self.assertGreater(self.m.mean, 0)

    def test_mean_correctness(self):
        """Mean must match the arithmetic mean of recorded data points."""
        for _ in range(3):
            time.sleep(0.005)
            self.m.lap()
        expected = sum(self.m.data_points) / len(self.m.data_points)
        self.assertAlmostEqual(self.m.mean, expected, places=10)

    def test_median_is_set(self):
        for _ in range(3):
            time.sleep(0.001)
            self.m.lap()
        self.assertGreater(self.m.median, 0)

    def test_stddev_is_zero_for_single_point(self):
        time.sleep(0.01)
        self.m.lap()
        # pstdev of a single-element population is 0
        self.assertEqual(self.m.stddev, 0.0)

    def test_rolling_window_caps_at_max_points(self):
        m = TimedMetric(name='capped')
        m.max_points = 5
        m.start()
        for _ in range(10):
            time.sleep(0.001)
            m.lap()
        self.assertEqual(len(m.data_points), 5)

    def test_to_dict_keys(self):
        time.sleep(0.01)
        self.m.lap()
        d = self.m.to_dict()
        expected_keys = {'name', 'data_point_count', 'mean', 'median', 'stddev'}
        self.assertEqual(set(d.keys()), expected_keys)

    def test_to_dict_data_point_count(self):
        time.sleep(0.005)
        self.m.lap()
        time.sleep(0.005)
        self.m.lap()
        d = self.m.to_dict()
        self.assertEqual(d['data_point_count'], 2)

    def test_to_dict_name(self):
        d = self.m.to_dict()
        self.assertEqual(d['name'], 'test')


class TestMetricsManager(unittest.TestCase):
    """Tests for the Metrics manager class."""

    def test_add_timing_element(self):
        m = Metrics()
        eid = m.add_element(MetricType.TIMING, name='latency')
        self.assertIsNotNone(eid)
        self.assertIsInstance(m.get(eid), TimedMetric)

    def test_add_counting_element(self):
        m = Metrics()
        eid = m.add_element(MetricType.COUNTING, name='ops')
        self.assertIsInstance(m.get(eid), CountMetric)

    def test_invalid_type_raises(self):
        m = Metrics()
        with self.assertRaises(ValueError):
            m.add_element('bogus')  # type: ignore[arg-type]

    def test_element_ids_are_unique(self):
        m = Metrics()
        ids = [m.add_element(MetricType.COUNTING) for _ in range(20)]
        self.assertEqual(len(set(ids)), 20)

    def test_get_data_timing(self):
        m = Metrics()
        eid = m.add_element(MetricType.TIMING, name='t')
        m.start(eid)
        time.sleep(0.01)
        m.lap(eid)
        d = m.get_data(eid)
        self.assertIn('mean', d)
        self.assertGreater(d['mean'], 0)

    def test_get_data_counting(self):
        m = Metrics()
        eid = m.add_element(MetricType.COUNTING, name='c')
        m.increment(eid)
        m.increment(eid)
        d = m.get_data(eid)
        self.assertEqual(d['count'], 2)

    def test_get_all_data_keyed_by_element_id(self):
        """Bug 2 regression: get_all_data() must return {element_id: data}, not a flat dict."""
        m = Metrics()
        t_id = m.add_element(MetricType.TIMING, name='latency')
        c_id = m.add_element(MetricType.COUNTING, name='ops')

        all_data = m.get_all_data()

        self.assertIn(t_id, all_data)
        self.assertIn(c_id, all_data)
        self.assertEqual(len(all_data), 2)

    def test_get_all_data_no_key_collision(self):
        """Two elements with the same name must not overwrite each other."""
        m = Metrics()
        id1 = m.add_element(MetricType.COUNTING, name='same')
        id2 = m.add_element(MetricType.COUNTING, name='same')

        m.increment(id1)
        m.increment(id1)
        m.increment(id2)

        all_data = m.get_all_data()
        self.assertEqual(all_data[id1]['count'], 2)
        self.assertEqual(all_data[id2]['count'], 1)

    def test_get_all_data_empty(self):
        m = Metrics()
        self.assertEqual(m.get_all_data(), {})

    def test_metric_type_enum_required(self):
        """Passing a raw string should raise ValueError, not silently succeed."""
        m = Metrics()
        with self.assertRaises((ValueError, AttributeError)):
            m.add_element('timing')  # type: ignore[arg-type]


class TestBaseMetricInstanceIsolation(unittest.TestCase):
    """Verify BaseMetric subclasses don't share mutable state."""

    def test_name_not_shared(self):
        a = CountMetric(name='a')
        b = CountMetric(name='b')
        self.assertIsNot(a.name, b.name)

    def test_is_base_metric(self):
        self.assertIsInstance(CountMetric(), BaseMetric)
        self.assertIsInstance(TimedMetric(), BaseMetric)


if __name__ == '__main__':
    unittest.main()
