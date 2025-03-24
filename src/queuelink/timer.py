# -*- coding: utf-8 -*-
"""Class to house time-related convenience functions."""
import datetime
import math  # pylint: disable=no-name-in-module
import time


class Timer:
    """Used to help time events."""
    SEC_TO_MICRO = 10**6
    SEC_TO_NANO = 10**9

    def __init__(self, interval: float=10):
        """Timing events: Establish start time reference for lap and interval

        Args:
            interval: Reference duration for ``interval`` method. Supports resolution to
                microseconds. Default is 10 seconds.
        """
        self.interval_period = interval
        self.start_time = self.now()
        self.start_moment_ns = time.perf_counter_ns()
        self.last_interval_count = 0

    @staticmethod
    def now() -> float:
        """Returns the current Unix epoch time

        Returns:
            Current Unix epoch time in integer seconds with decimal resolution to microseconds.
        """
        current = time.mktime(datetime.datetime.now().timetuple()) \
            + datetime.datetime.now().microsecond / float(Timer.SEC_TO_MICRO)

        return float(current)

    @staticmethod
    def now_micro() -> int:
        """Returns the current Unix epoch time in microseconds as an integer

        Returns:
            Current Unix epoch time in microseconds.
        """
        current = time.mktime(datetime.datetime.now().timetuple()) * Timer.SEC_TO_MICRO \
                  + datetime.datetime.now().microsecond

        return int(current)

    def lap_ns(self) -> int:
        """Return nanoseconds since this instance was created.

        Returns:
            Nanoseconds since this instance was created
        """
        return time.perf_counter_ns() - self.start_moment_ns

    def lap(self) -> float:
        """Return seconds since this instance was created.

        Includes decimal to nanosecond resolution, however, the division of nanoseconds is
        unreliable. Use ``lap_ns`` if high precision is required.

        Returns:
            Seconds since this instance was created (to nanoseconds)
        """
        return self.lap_ns() / Timer.SEC_TO_NANO

    def interval(self) -> bool:
        """Return True if we have exceeded the interval since we started or
        last called ``interval``.

        Returns:
            True if we have exceeded ``interval`` since we started or last called ``interval``,
                False otherwise.
        """

        # Get the current lap time
        lap = self.lap_ns()  # Nanoseconds
        interval = int(self.interval_period * Timer.SEC_TO_NANO)

        # How many intervals have elapsed since this instance was created?
        interval_count_float = lap / interval  # integer division

        # Round down the number of intervals to a whole number
        # pylint: disable=c-extension-no-member
        interval_count_floor = int(math.floor(interval_count_float))
        # pylint: enable=c-extension-no-member

        # If an interval has passed since the last one was recorded,
        # return true
        # pylint: disable=no-else-return
        if interval_count_floor > self.last_interval_count:
            self.last_interval_count = interval_count_floor
            return True
        else:
            return False
