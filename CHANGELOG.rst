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
