=========
Changelog
=========

All notable changes to this project will be documented here.

Format follows `Keep a Changelog <https://keepachangelog.com/en/1.1.0/>`_.
Versions correspond to git tags; unreleased changes appear under *Unreleased*.

----

Unreleased
----------

----

v2.3.1 — 2026-10-03
--------------------

Changed
~~~~~~~

- The default ``link_timeout`` for ``QueueLink`` and ``link()`` is now 0.1 s
  (was 0.01 s). An idle publisher now wakes about 10 times per second instead of
  about 100, cutting its idle CPU use by roughly 90%. Messages are not delayed,
  because a publisher's ``get()`` returns as soon as an item arrives. The
  trade-off is that ``stop()`` (and ``register_queue()``/``unregister_queue()``,
  which restart publishers) can now take up to about 100 ms per publisher to
  return, instead of about 10 ms. Pass ``link_timeout=0.01`` to keep the old
  behavior. The same timeout also governs how often a publisher retries a
  ``put()`` against a full, unconsumed destination: each failed attempt now
  blocks for up to 0.1 s before the stop event is re-checked and the attempt
  is retried, so a publisher stuck on a full destination now retries about 10
  times per second instead of about 100. This adds no delay under normal
  operation — a destination with room still accepts the item on the very next
  attempt, regardless of the timeout value. The trade-off mirrors the get
  side: if ``stop()`` is requested while a publisher is blocked retrying
  against a full destination, it can take up to the new timeout value longer
  to notice and abandon that destination (see the ``stop()`` entry under
  Fixed below for what "abandoned" means here). The same
  ``link_timeout=0.01`` opt-out restores the old retry cadence for puts as
  well (FEAT-010).

Fixed
~~~~~

- ``QueueLink.stop()``, ``register_queue(..., DIRECTION.TO)`` and
  ``unregister_queue()`` no longer hang forever when a destination queue is
  full and nobody is reading it. Publishers now put to destinations in bounded
  waits and check for a stop request between them. If a stop is requested while
  a destination is still full, that item is dropped for that destination only.
  Destinations with room still receive it, and a warning names the skipped
  destination(s) (FEAT-010).
- ``QueueLink.stop()``, ``register_queue(..., DIRECTION.TO)`` and
  ``unregister_queue()`` no longer hang forever when a process publisher has an
  *unbounded* ``multiprocessing.Queue``/``JoinableQueue`` destination that nobody
  reads and that holds more than the OS pipe buffer (about 64 KiB). The publisher
  process used to block at exit waiting for its feeder thread to flush into that
  pipe. A stopping publisher now gives its destinations up to ``link_timeout`` to
  flush. It then uses ``cancel_join_thread()`` on any that are still blocked,
  dropping the items left in its buffer for those destinations only, and logs a
  warning that lists the destinations. ``multiprocessing.SimpleQueue``
  destinations have no feeder thread; ``put()`` writes to the pipe directly
  on the calling thread/process, so it does not provide a timeout or retry. If
  such a destination is never read and its backlog passes the OS pipe buffer
  (about 64 KiB on Linux), that ``put()`` call blocks inside the OS write itself,
  which cannot be interrupted by checking the stop event, so ``stop()``,
  ``register_queue(..., DIRECTION.TO)``, and ``unregister_queue()`` can still
  hang forever for this one destination queue type (FEAT-010).

- ``QueueHandleAdapterWriter``: writing to a pipe, socket, or tty no longer
  crashes the writer thread/process with ``OSError: [Errno 22] Invalid
  argument`` — ``flush()`` now tolerates the ``EINVAL``/``ENOTSUP``/
  ``EOPNOTSUPP`` errors ``os.fsync()`` raises on handles that cannot be
  fsynced, while still raising on other, unexpected ``OSError``\ s (FEAT-010).
- ``QueueLink.get_queue()`` and ``QueueLink.is_empty()`` now accept an ``int``
  queue ID (e.g. the value returned by ``read()``/``write()`` cast back to
  ``int``) instead of raising ``KeyError``, matching the ``Union[str, int]``
  type hint both methods already declared (FEAT-010).
- ``QueueLink.unregister_queue()`` with ``direction=DIRECTION.FROM`` no longer
  raises ``KeyError`` when given a queue ID that was never registered
  (FEAT-010).
- ``QueueLink.close()`` and the internal handle-adapter ``close()`` no longer
  always attempt to stop an adapter/link that was never started — the check
  now correctly tests whether the "started" event is set, instead of the
  always-truthy ``Event`` object itself (FEAT-010).
- A destination queue that raises ``EOFError`` on ``put()`` no longer causes
  its publisher to busy-loop; the publisher now logs the final metrics and
  exits, the same as it already did for a ``BrokenPipeError`` (FEAT-010).
- ``register_queue()``/``unregister_queue()``/``destructive_audit()`` now
  accept ``direction`` as either a ``DIRECTION`` member or its string value
  (``"source"``/``"destination"``) consistently across all supported Python
  versions, and raise ``ValueError`` (previously a version-dependent
  ``TypeError`` that Python 3.12+ sometimes skipped) naming both valid values
  for anything else (FEAT-010).

----

v2.3.0 — 2026-09-27
--------------------

Added
~~~~~

- ``WriteMode`` enum (``BINARY`` / ``TEXT``) for explicit mode declaration on
  path-based handles passed to ``QueueHandleAdapterWriter``.  Exported from the
  top-level ``queuelink`` package.
- ``_is_binary_handle()`` internal helper — detects binary mode via the ``io``
  class hierarchy with fallback for wrapper objects (e.g.
  ``tempfile._TemporaryFileWrapper``) that do not subclass ``io.IOBase``
  directly.
- ``QueueHandleAdapterWriterWriteModeTest`` — six focused tests covering
  ``io.BytesIO`` / ``io.StringIO`` (no ``.mode`` attribute), mixed-type
  TypeError paths, and explicit ``WriteMode.BINARY`` / ``WriteMode.TEXT`` with
  path-based handles (FEAT-009).
- ``QueueLinkDynamicDestinationTest`` — tests for publisher stop-restart
  consistency guarantee when adding a destination to a running ``QueueLink``
  (FEAT-007).
- ``link()`` factory: fan-out to a list of mixed destinations — queues, file
  paths, and open handles — in a single call (FEAT-001).
- ``Metrics`` / ``TimedMetric`` / ``CountMetric`` — rebuilt metrics system with
  per-instance ``data_points`` lists and correct ``get_all_data()`` keying
  (FEAT-002).
- ``benchmarks/`` directory: ``throughput.py``, ``throughput_results.py``,
  ``throughput_test_exclude.py``, ``benchmarks/README.md`` (FEAT-003).
- ``log_exception()`` function in ``exceptionhandler.py`` — preferred
  replacement for ``ExceptionHandler`` class in new code (FEAT-004).
- ``_encoding.py`` — stdlib-only UTF-8 encoding helpers replacing the
  ``kitchen`` / ``processrunner-kitchenpatch`` runtime dependencies (FEAT-006).

Changed
~~~~~~~

- ``QueueHandleAdapterWriter``: binary mode is now determined once before the
  write loop via ``isinstance`` rather than being inferred from the first
  line's type.  Mixed-type streams now log an error and re-raise ``TypeError``
  so the worker exits cleanly and the failure is detectable via ``is_alive()``
  (FEAT-009).
- ``classtemplate.py`` / ``ClassTemplate`` renamed to ``logging_mixin.py`` /
  ``LoggingMixin`` across the entire codebase (FEAT-009 / REVIEW-001 item 12).
- ``register_queue()`` docstring updated with explicit consistency-guarantee
  language: all active publishers are stopped and restarted when a new
  destination is added (FEAT-007).
- ``ContentWrapper`` ``__setattr__`` / ``__getattr__`` descriptor pattern
  documented in class docstring (FEAT-005).
- ``link_timeout`` parameter documentation corrected; ``SimpleQueue`` polling
  behaviour documented in ``safe_get()`` (FEAT-005).
- ``writeout.py`` updated to use ``log_exception()`` and re-raise the original
  exception; removed ``ExceptionHandler`` call sites (FEAT-004).
- ``throughput.py`` and ``throughput_results.py`` relocated from
  ``src/queuelink/`` to ``benchmarks/`` — no longer installed as part of the
  library package (FEAT-003).
- Runtime dependency on ``kitchen`` / ``processrunner-kitchenpatch`` removed;
  replaced by ``_encoding.py`` (stdlib only) (FEAT-006).

Deprecated
~~~~~~~~~~

- ``ExceptionHandler`` class — use ``log_exception()`` instead.  Planned for
  removal in v3 alongside Windows support (FEAT-008).

Fixed
~~~~~

- ``is_alive()`` now returns ``False`` instead of raising ``ProcessNotStarted``
  when called before the adapter has been started (FEAT-004).
- ``BaseMetric.data_points`` was a mutable class attribute shared across all
  instances; moved to ``__init__`` (FEAT-002).
- ``Metrics.get_all_data()`` was merging all metric dicts by key, overwriting
  values from earlier elements; now keyed by ``element_id`` (FEAT-002).

----

v2.2.3 — 2026-03-25
--------------------

Fixed
~~~~~

- Metrics system rebuilt: ``BaseMetric.data_points`` moved to instance scope;
  ``get_all_data()`` now returns a dict keyed by ``element_id`` (FEAT-002).

----

v2.2.2 — 2026-03-25
--------------------

Changed
~~~~~~~

- CI job label updated to clarify TestPyPI-only publish step.

----

v2.2.1 — 2026-03-24
--------------------

Added
~~~~~

- ``link()`` factory function: inspects source/destination types and
  automatically wires ``QueueLink``, ``QueueHandleAdapterReader``, and/or
  ``QueueHandleAdapterWriter`` (FEAT-001).
- ``QueueHandleAdapterReader`` and ``QueueHandleAdapterWriter`` exported from
  top-level package.
- Agent workflow infrastructure: ``AGENTS.md``, ``tasks/`` directory, CI
  harness improvements.
- PyPI publish workflow added alongside existing TestPyPI step.

----

v2.1.0 — 2026-03-18
--------------------

Fixed
~~~~~

- Various lint findings resolved.

Changed
~~~~~~~

- CI test matrix: replaced ``macos-13`` with ``macos-15``, ``macos-26``, and
  ``macos-26-intel`` runners.
- Fork-context tests now run in parallel via ``pytest-xdist``; spawn/forkserver
  tests run serially in a second phase to avoid ``SemLock`` context conflicts.
- Branch ruleset and pre-commit configuration added.

----

v2.0.3 — 2025-07-19
--------------------

Changed
~~~~~~~

- Documentation migrated from ``pkg_resources`` to ``importlib_metadata`` for
  version detection.
- README and docs examples updated; project URLs capitalised.
- Contribution guide updated.

----

v1.0.0 — 2023-06-11
--------------------

Added
~~~~~

- Initial release.
