# -*- coding: utf-8 -*-
"""Factory function for automatically wiring sources and destinations together.

Pass in any supported source and destination and ``link()`` selects and
instantiates the correct combination of ``QueueLink``,
``QueueHandleAdapterReader``, and/or ``QueueHandleAdapterWriter``.
"""
from __future__ import unicode_literals

import multiprocessing
import time

from enum import Enum
from io import IOBase
from os import PathLike

from multiprocessing.managers import BaseProxy

from .common import DIRECTION, THREADED_QUEUES
from .contentwrapper import WRAP_WHEN
from .exceptionhandler import ProcessNotStarted
from .queue_handle_adapter_reader import QueueHandleAdapterReader
from .queue_handle_adapter_writer import QueueHandleAdapterWriter
from .queuelink import QueueLink


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

class _EndpointKind(Enum):
    """Endpoint type classification for link() sources and destinations."""
    QUEUE = 'queue'
    HANDLE = 'handle'
    PATH = 'path'
    CONNECTION = 'connection'


def _is_queue(obj) -> bool:
    """Return True if obj is a supported queue type."""
    if isinstance(obj, tuple(THREADED_QUEUES)):
        return True

    if isinstance(obj, (
        multiprocessing.queues.Queue,
        multiprocessing.queues.JoinableQueue,
        multiprocessing.queues.SimpleQueue,
    )):
        return True
    # Manager-backed proxy queues — check for queue interface
    if isinstance(obj, BaseProxy) and all(
        hasattr(obj, m) for m in ('put', 'get', 'empty')
    ):
        return True
    return False


def _classify(obj, role: DIRECTION = None) -> _EndpointKind:
    """Classify an endpoint object.

    Args:
        obj: The source or destination object to classify.
        role: ``DIRECTION.FROM`` or ``DIRECTION.TO`` — used for handle IO
            contract checks. If ``None``, contract checks are skipped.

    Returns:
        ``_EndpointKind`` enum value (QUEUE, HANDLE, PATH, or CONNECTION).

    Raises:
        TypeError: For unsupported types, QueueLink/``_LinkResult`` instances,
            or handles that do not satisfy the required IO contract.
    """
    # Reject QueueLink and _LinkResult instances immediately
    if isinstance(obj, QueueLink):
        raise TypeError(
            f"QueueLink instances are not accepted as link() endpoints. "
            f"Got: {type(obj).__name__}"
        )

    if isinstance(obj, _LinkResult):
        raise TypeError(
            f"_LinkResult instances are not accepted as link() endpoints. "
            f"Got: {type(obj).__name__}"
        )

    # Queue types (precedence: before path, since str/PathLike are also checked)
    if _is_queue(obj):
        return _EndpointKind.QUEUE

    # Connection (before generic handle check)
    if isinstance(obj, multiprocessing.connection.Connection):
        if role == DIRECTION.TO:
            raise TypeError(
                "multiprocessing.connection.Connection is not supported as a "
                "destination in this version. "
                "Pass a queue or file path/handle as the destination."
            )

        return _EndpointKind.CONNECTION

    # File paths
    if isinstance(obj, (str, PathLike)):
        return _EndpointKind.PATH

    # IO handles / duck-typed handles
    if isinstance(obj, IOBase) or (hasattr(obj, 'read') or hasattr(obj, 'write')):
        if role == DIRECTION.FROM and not hasattr(obj, 'readline'):
            raise TypeError(
                f"Source handle {type(obj).__name__!r} must support readline(). "
                "Wrap it with codecs.getreader() or provide a readline-capable handle."
            )

        if role == DIRECTION.TO and not hasattr(obj, 'write'):
            raise TypeError(
                f"Destination handle {type(obj).__name__!r} must support write()."
            )

        return _EndpointKind.HANDLE

    raise TypeError(
        f"Unsupported endpoint type: {type(obj).__name__!r}. "
        "Supported types: queue (queue.Queue, multiprocessing.Queue, etc.), "
        "file handle (IOBase or readline/write duck type), "
        "file path (str or PathLike), "
        "or multiprocessing.connection.Connection (source only)."
    )


def _normalize_destination(destination):
    """Return destination as a list, validating along the way.

    Raises:
        TypeError: For non-list iterables or QueueLink instances.
        ValueError: For empty lists or duplicate objects.
    """
    dests = []  # Will hold destination(s) as a list
    if isinstance(destination, list):
        dests = destination
    elif isinstance(destination, (tuple, set)):
        raise TypeError(
            "destination must be a single endpoint or a list of endpoints. "
            f"Got {type(destination).__name__!r}. Use a list for multiple destinations."
        )
    else:
        dests = [destination]

    if len(dests) == 0:
        raise ValueError("destination list must not be empty.")

    # Check for duplicates by identity
    seen_ids = set()
    for d in dests:
        obj_id = id(d)
        if obj_id in seen_ids:
            raise ValueError(
                f"Duplicate destination object detected: {type(d).__name__!r}. "
                "Each destination must be a distinct object."
            )
        seen_ids.add(obj_id)

    return dests


# ---------------------------------------------------------------------------
# Internal result container
# ---------------------------------------------------------------------------

class _LinkResult:  # pylint: disable=too-few-public-methods
    """Container for the components created by ``link()``.

    Not exported from the package. Users obtain an instance by calling
    ``link()`` and interact with it via ``stop()``, ``close()``, and
    ``is_alive()``.

    For queue→queue links, ``result.queue_link`` provides direct access to the
    underlying ``QueueLink`` for advanced operations (``is_empty``,
    ``is_drained``, ``get_metrics``, etc.).
    """

    def __init__(self):
        self.queue_link = None                 # QueueLink; None for adapter-only paths
        self.reader = None                     # QueueHandleAdapterReader or None
        self.writers = []                      # List of QueueHandleAdapterWriter
        self._internal_queues = []             # Queues created internally by link()
        self._drain_timeout = 5.0             # Max seconds to wait for internal queue drain

    def stop(self):
        """Stop all managed components in the correct order.

        Order:
        1. Stop the reader first (halts upstream production).
        2. Wait (bounded) for internal queues to drain into downstream stages.
        3. Stop the QueueLink publishers (if present).
        4. Stop writer adapters last (downstream sinks).
        """
        # 1. Stop reader
        if self.reader is not None:
            self.reader.close()

        # 2. Wait for internal queues to drain (best-effort, bounded)
        if self._internal_queues:
            deadline = time.monotonic() + self._drain_timeout
            for q in self._internal_queues:
                while time.monotonic() < deadline:
                    try:
                        if q.empty():
                            break
                    except OSError:
                        # Queue closed/broken (handle closed, manager shutdown, etc.)
                        break
                    time.sleep(0.01)

        # 3. Stop QueueLink
        if self.queue_link is not None:
            self.queue_link.stop()

        # 4. Stop writers
        for writer in self.writers:
            writer.close()

    def close(self):
        """Alias for ``stop()`` — consistent with adapter usage patterns."""
        self.stop()

    def is_alive(self) -> bool:
        """Return True if any managed worker thread/process is still alive."""
        if self.reader is not None and self.reader.is_alive():
            return True

        if self.queue_link is not None:
            try:
                if self.queue_link.is_alive():
                    return True
            except ProcessNotStarted:
                # QueueLink never started; treat as not alive
                pass

        for writer in self.writers:
            if writer.is_alive():
                return True

        return False


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def link(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements,protected-access
        source,
        destination,
        *,
        name: str = None,
        start_method: str = None,
        thread_only: bool = False,
        trusted: bool = False,
        wrap_when: WRAP_WHEN = WRAP_WHEN.NEVER,
        wrap_threshold: int = None,
        link_timeout: float = 0.01):
    """Wire a source and destination together automatically.

    Inspects the types of ``source`` and ``destination`` and creates the
    appropriate combination of ``QueueLink``, ``QueueHandleAdapterReader``,
    and/or ``QueueHandleAdapterWriter``.

    Args:
        source: A queue, open file/pipe handle, file path (str/PathLike), or
            ``multiprocessing.connection.Connection`` to read from.
        destination: A queue, open file/pipe handle, or file path to write to.
            May also be a ``list`` of such objects for fan-out. Tuples and
            sets are not accepted (use a list).
        name: Optional name passed to created components for logging.
        start_method: Multiprocessing start method (``'fork'``,
            ``'forkserver'``, ``'spawn'``). Defaults to system preference.
        thread_only: Force threading instead of separate processes.
        trusted: For ``Connection`` sources — if ``True``, use
            ``.recv()``/``.send()``; if ``False``, use ``.recv_bytes()``.
        wrap_when: When to wrap large messages in ``ContentWrapper`` for disk
            buffering. Only applies when a reader adapter is created.
        wrap_threshold: Byte size limit before wrapping. Only relevant when
            ``wrap_when`` is ``WRAP_WHEN.AUTO``.
        link_timeout: ``queue.get()`` timeout for ``QueueLink`` publishers.

    Returns:
        A ``_LinkResult`` instance with ``stop()``, ``close()``, and
        ``is_alive()`` interface. For queue→queue links, ``result.queue_link``
        exposes the underlying ``QueueLink``.

    Raises:
        TypeError: If either endpoint is an unsupported type, a
            ``QueueLink``/``_LinkResult`` instance, a ``Connection`` as
            destination, or if ``destination`` is a non-list iterable.
        ValueError: If ``destination`` is an empty list or contains
            duplicate objects.
    """
    # Normalise destination to a list
    dests = _normalize_destination(destination)

    # Classify source
    src_kind = _classify(source, role=DIRECTION.FROM)

    # Classify all destinations
    dest_kinds = [_classify(d, role=DIRECTION.TO) for d in dests]

    # Guard: Connection source to any handle/path destination is deferred
    if (src_kind == _EndpointKind.CONNECTION and
            any(k in (_EndpointKind.HANDLE, _EndpointKind.PATH) for k in dest_kinds)):
        raise TypeError(
            "Connection source to file handle/path destinations is not supported "
            "in this version. Use a queue as the destination when sourcing from "
            "a multiprocessing.connection.Connection."
        )

    result = _LinkResult()

    # Context for creating internal queues
    ctx = multiprocessing.get_context(start_method)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    all_queue_dests = all(k == _EndpointKind.QUEUE for k in dest_kinds)
    single_dest = len(dests) == 1

    if src_kind == _EndpointKind.QUEUE:
        if all_queue_dests:
            # queue → queue (or list of queues): delegate entirely to QueueLink
            dest_arg = dests[0] if single_dest else dests
            ql = QueueLink(
                source=source,
                destination=dest_arg,
                name=name,
                start_method=start_method,
                thread_only=thread_only,
                link_timeout=link_timeout,
            )
            result.queue_link = ql

        else:
            # queue → handle/path (single or mixed fan-out)
            # For each destination:
            #   - queue dest: register directly on QueueLink
            #   - handle/path dest: create internal queue + writer
            ql = QueueLink(
                source=source,
                name=name,
                start_method=start_method,
                thread_only=thread_only,
                link_timeout=link_timeout,
            )
            result.queue_link = ql

            for dest, kind in zip(dests, dest_kinds):
                if kind == _EndpointKind.QUEUE:
                    ql.write(q=dest)
                else:
                    # handle or path: create internal queue → writer
                    internal_q = ctx.Queue()
                    result._internal_queues.append(internal_q)
                    ql.write(q=internal_q)
                    writer = QueueHandleAdapterWriter(
                        queue=internal_q,
                        handle=dest,
                        name=name,
                        start_method=start_method,
                        thread_only=thread_only,
                    )
                    result.writers.append(writer)

    elif src_kind in (_EndpointKind.HANDLE, _EndpointKind.PATH, _EndpointKind.CONNECTION):

        if all_queue_dests and single_dest:
            # handle/path/connection → single queue: just a reader adapter
            reader = QueueHandleAdapterReader(
                queue=dests[0],
                handle=source,
                name=name,
                start_method=start_method,
                thread_only=thread_only,
                trusted=trusted,
                wrap_when=wrap_when,
                wrap_threshold=wrap_threshold,
            )
            result.reader = reader

        elif all_queue_dests and not single_dest:
            # handle/path/connection → [queue, queue, ...]
            # reader → internal queue → QueueLink fan-out
            internal_q = ctx.Queue()
            result._internal_queues.append(internal_q)

            reader = QueueHandleAdapterReader(
                queue=internal_q,
                handle=source,
                name=name,
                start_method=start_method,
                thread_only=thread_only,
                trusted=trusted,
                wrap_when=wrap_when,
                wrap_threshold=wrap_threshold,
            )
            result.reader = reader

            ql = QueueLink(
                source=internal_q,
                destination=dests,
                name=name,
                start_method=start_method,
                thread_only=thread_only,
                link_timeout=link_timeout,
            )
            result.queue_link = ql

        elif src_kind == _EndpointKind.CONNECTION:
            # Connection → mixed destinations: not supported in this version
            raise TypeError(
                "Connection source to mixed (queue + handle/path) destinations "
                "is not supported in this version."
            )

        elif single_dest:
            # handle/path → single handle/path: reader → internal queue → writer
            internal_q = ctx.Queue()
            result._internal_queues.append(internal_q)

            reader = QueueHandleAdapterReader(
                queue=internal_q,
                handle=source,
                name=name,
                start_method=start_method,
                thread_only=thread_only,
                trusted=trusted,
                wrap_when=wrap_when,
                wrap_threshold=wrap_threshold,
            )
            result.reader = reader

            writer = QueueHandleAdapterWriter(
                queue=internal_q,
                handle=dests[0],
                name=name,
                start_method=start_method,
                thread_only=thread_only,
            )
            result.writers.append(writer)

        else:
            # handle/path → [mixed destinations]
            # reader → internal queue → QueueLink → per-dest
            internal_q = ctx.Queue()
            result._internal_queues.append(internal_q)

            reader = QueueHandleAdapterReader(
                queue=internal_q,
                handle=source,
                name=name,
                start_method=start_method,
                thread_only=thread_only,
                trusted=trusted,
                wrap_when=wrap_when,
                wrap_threshold=wrap_threshold,
            )
            result.reader = reader

            ql = QueueLink(
                source=internal_q,
                name=name,
                start_method=start_method,
                thread_only=thread_only,
                link_timeout=link_timeout,
            )
            result.queue_link = ql

            for dest, kind in zip(dests, dest_kinds):
                if kind == _EndpointKind.QUEUE:
                    ql.write(q=dest)
                else:
                    fan_q = ctx.Queue()
                    result._internal_queues.append(fan_q)
                    ql.write(q=fan_q)
                    writer = QueueHandleAdapterWriter(
                        queue=fan_q,
                        handle=dest,
                        name=name,
                        start_method=start_method,
                        thread_only=thread_only,
                    )
                    result.writers.append(writer)

    return result
