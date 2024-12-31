# -*- coding: utf-8 -*-
"""QueueLink allows you to easily connect queues together"""
# Define version variable
from importlib_metadata import version, packages_distributions, PackageNotFoundError

from queuelink.queuelink import QueueLink
from queuelink.queuelink import UNION_SUPPORTED_QUEUES
from queuelink.timer import Timer

try:
    packages = packages_distributions()
    package_name = packages[__name__][0]
    __version__ = version(package_name)
except (PackageNotFoundError, KeyError):
    # package is not installed
    pass
