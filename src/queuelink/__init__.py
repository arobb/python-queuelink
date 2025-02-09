# -*- coding: utf-8 -*-
"""QueueLink allows you to easily connect queues together"""
# Define version variable
from importlib_metadata import version, packages_distributions, PackageNotFoundError

from queuelink import common

from queuelink.queuelink import QueueLink
from queuelink.timer import Timer
from queuelink.common import UNION_SUPPORTED_QUEUES

# Pipe adapters
from queuelink.contentwrapper import ContentWrapper
from queuelink.contentwrapper import WRAP_WHEN
from queuelink.writeout import writeout
from queuelink.queue_handle_adapter_reader import QueueHandleAdapterReader

try:
    packages = packages_distributions()
    package_name = packages[__name__][0]
    __version__ = version(package_name)
except (PackageNotFoundError, KeyError):
    # package is not installed
    pass
