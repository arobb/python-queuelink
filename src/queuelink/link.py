"""Simplifies selection of adapters/QueueLink

Pass in the source and destination and link will return an appropriate class instance.
"""
from io import IOBase
from typing import Union

from .common import UNION_SUPPORTED_QUEUES
from .queue_handle_adapter_reader import QueueHandleAdapterReader
from .queue_handle_adapter_writer import QueueHandleAdapterWriter


def link(read: Union[UNION_SUPPORTED_QUEUES],
         write: Union[QueueLink, QueueHandleAdapterWriter]):
    pass
