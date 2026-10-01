# REVIEW-002: Correctness, ContentWrapper Lifecycle, and Housekeeping Review

**Date**: 2026-09-28
**Scope**: Full source read, test suite run (1828 passed / 30 skipped, Python 3.11, Linux),
targeted reproduction scripts for suspected bugs
**Status**: Triaged — all items mapped to FEAT-010 through FEAT-014.
FEAT-010 (items 1–6, 22, and its share of 24) resolved 2026-09-29 — see each
item's "Resolved" note and `tasks/FEAT-010/` for detail. FEAT-011 through
FEAT-014 remain open.

This document captures findings and recommendations. It is not an implementation
plan — it is input to prioritization decisions. Items have been triaged into
`tasks/TODO.md` as FEAT-010 through FEAT-014.

Items marked **(reproduced)** were confirmed with a runnable script; the script
logic is summarized in the relevant FEAT plan so it can become a regression test.

---

## Bugs

### 1. Publisher cannot stop while blocked on a full destination (queuelink.py `_publisher`) **(reproduced)** → FEAT-010 ✅ Resolved (FEAT-010)

`_publisher` calls `dest_queue.put(line)` with no timeout. If any destination has
a `maxsize` and is not being consumed, the publisher blocks forever and never
re-checks `stop_event`. `_stop_publisher` then loops on `join(timeout=1)`
indefinitely. Because `register_queue(TO)` and `unregister_queue` stop all
publishers first, registering a destination can also hang.

Repro: `queue.Queue()` source, `queue.Queue(maxsize=1)` destination, put 3 items,
call `stop()` in a thread — still alive after 5 s.

**Fix**: bounded `put(timeout=…)` in a loop that checks `stop_event`. Consider
together with polling behavior on the get side (item 22 merged here). A shutdown
sentinel cannot help this case: the publisher is blocked on the put side and will
never read a sentinel placed in the source queue.

**Resolved**: `_put_until_stopped`/`_fan_out` in `queuelink.py` — bounded,
retrying puts that re-check `stop_event`; a destination still full when stop is
requested is abandoned (logged), destinations with room still receive the item.
While implementing this, a related liveness gap was found and fixed in the same
feature (not part of the original repro): a process publisher whose *unbounded*
`multiprocessing.Queue`/`JoinableQueue` destination goes unread can still hang at
process exit, because Python joins that queue's feeder thread before the process
can exit. Fixed with a bounded flush followed by `cancel_join_thread()` for
destinations still unflushed (`_release_destinations`; process publishers only).
See `tasks/FEAT-010/DECISIONS.md` Q5 for the full rationale and the residual,
undocumented-as-fixed case (`multiprocessing.SimpleQueue`, no feeder thread —
documented limitation, not fixed). Regression tests:
`QueueLinkFullDestinationStopTest`, `QueueLinkFullDestinationStopProcessTest`,
`QueueLinkUnreadDestinationStopProcessTest`, `QueueLinkStopFlushesDestinationTest`,
`QueueLinkThreadPublisherLeavesDestinationOpenTest`.

---

### 2. Writer adapter crashes on pipes: `os.fsync` → `EINVAL` (queue_handle_adapter_writer.py `flush`) **(reproduced)** → FEAT-010 ✅ Resolved (FEAT-010)

`flush()` calls `os.fsync(file_handle.fileno())` whenever `fileno` exists. On a
subprocess stdin pipe this raises `OSError: [Errno 22] Invalid argument` on Linux.
The data had already been written, but the worker thread dies with a traceback.

**Fix**: catch `OSError` with `errno in (EINVAL, ENOTSUP)` (or only fsync when
`os.fstat(fd)` reports a regular file).

**Resolved**: `flush()` now catches `OSError` and ignores it only when `errno`
is `EINVAL`/`ENOTSUP`/`EOPNOTSUPP`, re-raising anything else. Regression test:
`QueueHandleAdapterWriterFsyncPipeTest`.

---

### 3. `get_queue(int)` / `is_empty(int)` raise `KeyError` for source queues (queuelink.py) **(reproduced)** → FEAT-010 ✅ Resolved (FEAT-010)

Signature advertises `Union[str, int]`, but the membership check
`queue_id in self.client_queues_source` uses the raw int against `str` keys, so it
falls through to the destination dict and raises `KeyError`. `is_empty(queue_id)`
has the same pattern.

**Fix**: normalize with `str(queue_id)` before any membership test.

**Resolved**: `get_queue`/`is_empty` normalize with `text(queue_id)` before
membership tests; `unregister_queue(FROM)` also now guards against an unknown
id instead of raising `KeyError` from `publisher_stops.pop`. Regression tests:
`QueueLinkIntQueueIdTest`.

---

### 4. `close()` tests an Event object for truthiness (queuelink.py, queue_handle_adapter_base.py) → FEAT-010 ✅ Resolved (FEAT-010)

`if self.started:` is always true for an Event instance; should be
`self.started.is_set()`. Currently harmless-ish (causes an unnecessary `stop()`),
but misleading and fragile.

**Resolved**: both `close()` methods (`QueueLink` and
`_QueueHandleAdapterBase`) now check `self.started is not None and
self.started.is_set()`.

---

### 5. `_publisher` busy-loops on `EOFError` → FEAT-010 ✅ Resolved (FEAT-010)

The `except EOFError` branch logs and falls through to the next loop iteration
without returning. If a destination has gone away, the loop spins. Should
`return` (matching the `BrokenPipeError` branch).

**Resolved**: the `EOFError` branch now emits final metrics and `return`s, the
same as the stop-event path. Regression test: `QueueLinkEOFErrorTest`.

---

### 6. `direction` as a plain string behaves differently across Python versions **(reproduced)** → FEAT-010 ✅ Resolved (FEAT-010)

`validate_direction` uses `arg_direction in DIRECTION`. For a `str`, Python
3.9–3.11 raise `TypeError: unsupported operand type(s) for 'in'`; 3.12+ return
`True` for a matching value. Behavior should not depend on the interpreter.
The explicit `raise TypeError("destination must be a value from DIRECTION")` should
also be `ValueError`, and the message mentions "destination" for either direction.

**Fix**: normalize (`DIRECTION(value)` when given a str) or reject explicitly with
a clear `ValueError`.

**Resolved**: `validate_direction` now accepts a `DIRECTION` member or converts
a string via `DIRECTION(value)`; anything else raises `ValueError` naming both
valid values. Version-independent (no longer relies on `Enum.__contains__`).
Regression tests: `QueueLinkDirectionStrTest`.

---

## ContentWrapper Design Issues

Context: ContentWrapper exists to help drain OS pipes of unknown size (e.g. stdout
of a long-running process) without memory pressure. It is opt-in (`WRAP_WHEN.NEVER`
is the default on the reader and on `link()`), and should remain opt-in. The issues
below are about correctness and lifecycle once it is turned on.

### 7. Spilled ContentWrapper breaks under fan-out **(reproduced)** → FEAT-011

Fanning out a file-backed ContentWrapper to two process queues gives both consumers
a copy that points at the same temp file. The first copy's `__del__` deletes it;
the second consumer fails in `__setstate__` with `FileNotFoundError`.

Separately, fan-out to **thread** queues puts the *same object* into every
destination (reproduced: `a is b` → True, and reassigning `a.value` changed
`b.value`). Process destinations receive discrete objects via pickling.

**Fix**: publisher calls `cw.clone_for_destination()` for every ContentWrapper
before every `put()`, for all queue types. In-memory: shallow copy (the wrapped
`str`/`bytes` is immutable). File-backed: new wrapper + hard link to the spill
file, falling back to a copy on `OSError` (no OS detection — link support is a
filesystem property; Windows NTFS supports `os.link`, while FAT/exFAT, some
network/FUSE mounts, and cross-device links do not).

---

### 8. `.value` reassignment returns stale data or appends **(reproduced)** → FEAT-011

- Small → large: `cw.value` still returns the old small value. The guard
  `hasattr(object, 'value')` tests the builtin `object` class (always False), so
  the old in-memory value is never removed; because it remains in `__dict__`,
  `__getattr__` is never invoked.
- Large → large: the second value is appended to the first. The temp file is not
  `seek(0)`/`truncate()`d before writing.

**Fix**: copy-on-write setter — reassignment writes a *new* file under a new name
and unlinks this wrapper's old name; never rewrite a file in place. This keeps
hard-linked siblings intact (item 7) and remains backward compatible.

---

### 9. Cleanup relies on `__del__` → FEAT-011

`__del__` is not guaranteed at interpreter exit and runs in GC order during
teardown. `_delete_temp_file` also calls `os.remove` without tolerating
`FileNotFoundError`.

**Fix**: `weakref.finalize` (idempotent, runs at exit) and tolerant deletion. Exactly
one owner deletes each file name.

### 10. No explicit release → FEAT-011

**Fix**: `ContentWrapper.close()` and context-manager support so consumers can
release the spill file as soon as they have read the value.

### 11. Spill files are anonymous `tmpXXXX` files in the system temp dir → FEAT-011

**Fix**: per-run `tempfile.mkdtemp(prefix="queuelink-")` directory and a configurable
`spill_dir` (lets users choose tmpfs or a specific volume).

### 12. No recovery from crash leftovers → FEAT-011

**Fix**: optional sweep of `queuelink-*` directories whose owning PID is no longer
alive (PID in directory name or marker file). Opt-in or clearly documented —
deleting in a shared temp directory must never surprise anyone.

### 13. `location_handle` is held open for the wrapper's lifetime → FEAT-011

Keeping the handle open is unnecessary and blocks deletion on Windows (Python's
`open()` does not use `FILE_SHARE_DELETE`). Relevant to FEAT-008.

**Fix**: open only for the duration of a read or write.

### 14. Documentation gaps → FEAT-011

Document: spilling is opt-in; where spill files live and data-at-rest implications
(application-level encryption intentionally out of scope — full-disk encryption is
the expected control); thread-queue fan-out shares object references for user
objects (same as stdlib), but ContentWrapper is cloned per destination.

Note: `NamedTemporaryFile` / `mkstemp` already create files with mode 0600 — no
change needed. Overwrite-before-unlink is intentionally not recommended: it is not
reliable on SSDs or copy-on-write filesystems (APFS, btrfs).

---

### 15. Oversized single lines are fully buffered in memory before spilling → FEAT-012

The reader calls `handle.readline()`, which materializes the entire line in memory,
and only then `conditional_wrap()` writes it to disk. A multi-GB line without a
newline therefore still costs its full size in RAM at peak. Spilling only avoids
downstream copies (pickle buffer, pipe, consumer).

**Fix**: streaming `SpillWriter` builder — `read(chunk_size)` straight into a spill
file until newline/EOF, then `seal()` returns an immutable ContentWrapper.

---

### 16. No overflow policy for queue backlog → FEAT-013 (proposal)

Per-message spill does not address the common failure mode of many normal-size
lines arriving faster than the consumer drains them. Options: backpressure
(`block`), `drop_oldest`, or a spill-backed buffer inside the reader adapter.
Proposal only; not scheduled.

---

## Consistency and Structural

### 17. README rationale for spill-to-disk is outdated → FEAT-014

README says spilling avoids "pipe size limits." A 200 MB string passes through a
plain `multiprocessing.Queue` under both fork and spawn. The cited 2011 article
describes a join-before-consume deadlock, not a message size limit. The real
rationale is draining OS pipes of unknown size without memory pressure.

### 18. Unnecessary runtime dependency on `importlib_metadata` → FEAT-014

Used only to call `packages_distributions()` in `__init__.py`. Stdlib
`importlib.metadata.version("queuelink")` is sufficient on all supported versions,
leaving zero runtime dependencies.

### 19. Three packaging config sources → FEAT-014

`setup.py`, `setup.cfg`, and `pyproject.toml`. `name` is under `[options]` rather
than `[metadata]` in `setup.cfg`. Consolidate into `pyproject.toml` (tox and
tool configs can move to `tox.ini` / `[tool.*]`).

### 20. Python version matrix → FEAT-014

3.9 is end-of-life (October 2025). 3.14 is absent from CI; it matters for this
library (free-threaded builds, start-method defaults).

### 21. Python 2 remnants and typing → FEAT-014

`from __future__ import unicode_literals`, `from builtins import str as text`,
`any` used as a type (should be `typing.Any`). No static type checking in CI.

### 22. Polling timeouts → merged into item 1 / FEAT-010 ✅ Resolved (FEAT-010)

The 10 ms `link_timeout` does **not** add message latency (`get(timeout=)` returns
as soon as an item arrives); it controls stop responsiveness and idle wakeups.
Raising the default to ~100–250 ms cuts idle wakeups 10–25×. A get-side sentinel
was considered and deferred: it enters a queue QueueLink does not own, misorders in
Priority/Lifo queues, can block on a full source, and needs per-generation tokens to
survive publisher restarts. `queue.SimpleQueue.get()` supports `timeout=` (3.7+);
the polling path only applies to `multiprocessing.SimpleQueue` — the `safe_get`
docstring says otherwise.

**Resolved**: default `link_timeout` raised to 0.1 s (from 0.01 s), reused for
the put-side retry timeout — measured ~9× idle-CPU reduction, throughput
unchanged within noise (see `tasks/FEAT-010/PROGRESS.md` Benchmarks). No
get-side sentinel added, per the rationale above (recorded in
`tasks/FEAT-010/DECISIONS.md`). `safe_get` docstring corrected.

### 23. Agent scaffolding at repo root → FEAT-014

`tasks/`, `AGENTS.md`, `.cursor/`, `.aiassistant/`, `.claude/`, `HARNESS.md` are the
first things a new contributor sees. Consider consolidating under a single
directory. (Open question in FEAT-014 — AGENTS.md conventions reference `tasks/`
paths.)

### 24. Regression tests for reproduced bugs → FEAT-010, FEAT-011

Each reproduced item above should land with a test that fails before the fix.

**FEAT-010 portion resolved**: every reproduced FEAT-010 item above has a
regression test (see each item's own "Resolved" note for the specific test
names); each was confirmed to fail against the pre-fix code and pass after.
FEAT-011's portion (ContentWrapper fan-out/`.value` reassignment) remains open.

---

## Prioritization Summary

| # | Area | Severity | Effort | Status |
|---|---|---|---|---|
| 1 | Publisher stop hangs on full destination | **High** (liveness) | Medium | ✅ Resolved (FEAT-010) |
| 2 | Writer `fsync` on pipes | **High** (correctness) | Low | ✅ Resolved (FEAT-010) |
| 3 | `get_queue(int)` / `is_empty(int)` KeyError | Medium (correctness) | Low | ✅ Resolved (FEAT-010) |
| 4 | `if self.started:` Event truthiness | Low (correctness) | Low | ✅ Resolved (FEAT-010) |
| 5 | `_publisher` busy-loop on EOFError | Medium (reliability) | Low | ✅ Resolved (FEAT-010) |
| 6 | `direction` str behavior varies by version | Low (API consistency) | Low | ✅ Resolved (FEAT-010) |
| 7 | ContentWrapper fan-out (shared file / shared object) | **High** (data loss) | Medium | Open — FEAT-011 |
| 8 | `.value` reassignment stale/append | **High** (correctness) | Low | Open — FEAT-011 |
| 9 | `__del__`-based cleanup | Medium (reliability) | Low | Open — FEAT-011 |
| 10 | No explicit release | Low (API) | Low | Open — FEAT-011 |
| 11 | Anonymous spill files | Low (operability) | Low | Open — FEAT-011 |
| 12 | Crash leftover sweep | Low (operability) | Medium | Open — FEAT-011 |
| 13 | Long-held `location_handle` | Low (portability) | Low | Open — FEAT-011 |
| 14 | ContentWrapper docs | Low (docs) | Low | Open — FEAT-011 |
| 15 | Oversized lines buffered in memory | **High** (memory) | Medium | Open — FEAT-012 |
| 16 | Backlog overflow policy / durable spill | Medium (feature) | High | Proposal — FEAT-013 |
| 17 | README spill rationale | Low (docs) | Low | Open — FEAT-014 |
| 18 | `importlib_metadata` dependency | Low (packaging) | Low | Open — FEAT-014 |
| 19 | Packaging config consolidation | Low (packaging) | Medium | Open — FEAT-014 |
| 20 | Python version matrix | Medium (support) | Low | Open — FEAT-014 |
| 21 | Py2 remnants / typing | Low (cleanliness) | Low | Open — FEAT-014 |
| 22 | Polling timeouts | Low (efficiency) | Low | ✅ Resolved (FEAT-010) |
| 23 | Agent scaffolding location | Low (structure) | Low | Open — FEAT-014 |
| 24 | Regression tests | Medium (quality) | Low | ✅ Resolved (FEAT-010); Open (FEAT-011) |
