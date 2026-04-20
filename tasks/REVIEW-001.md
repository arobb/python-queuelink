# REVIEW-001: Architectural Review — python-queuelink

**Date**: 2026-03-22
**Scope**: Full source and test read
**Status**: Open — items pending triage into task board

This document captures findings and recommendations. It is not an implementation
plan — it is input to prioritization decisions. Open items should be converted
to `tasks/TODO.md` entries (features or standalone tasks) before being actioned.

---

## Bugs

### 1. `BaseMetric.data_points` is a mutable class attribute (metrics.py:34) ✅ Resolved (FEAT-002)

```python
class BaseMetric(ClassTemplate):
    data_points = []   # ← shared across ALL instances
```

This is a classic Python footgun. Because `data_points` is defined at class
scope, all `TimedMetric` instances share the same list. Appending a data point
to one metric affects every other metric. The symptom would be metrics showing
wildly incorrect values as the list fills with mixed data from all active
publishers.

**Fix**: Move to `__init__`:
```python
def __init__(self, ...):
    self.data_points = []
```

The same issue affects `name`, `max_points`, `count`, `mean`, `median`, and
`stddev` — although scalars are shadowed correctly by instance assignment, the
list is not.

---

### 2. `Metrics.get_all_data()` merges keys destructively (metrics.py:183–193) ✅ Resolved (FEAT-002)

```python
return {k: v for d in data_list for k, v in d.items()}
```

`get_data()` returns dicts like `{'name': 'x', 'mean': 0.5, 'count': 1}`.
Merging them by key means the second element's `name` key overwrites the
first's, and so on for every shared key. The result is a single flat dict
containing only the last element's values for each key name — not a useful
aggregate.

**Fix**: Key by `element_id`:
```python
return {eid: self.get_data(eid) for eid in self.elements}
```

---

## Design Issues

### 3. Adding a destination restarts all publishers (queuelink.py)

When a new destination queue is registered, `register_queue()` stops every
active publisher and restarts them all with the updated destination dict. For
$n$ source queues, one new destination causes $n$ publisher restarts, each
of which may involve process creation overhead.

**Design rationale (confirmed with original author 2026-04-19):**

The stop-and-restart enforces a specific consistency invariant: every message
put to a source queue *after* `register_queue()` returns will be delivered to
*all* registered destinations, including the newly added one.

Without the restart this invariant cannot be guaranteed:

- **Process-based publishers** (spawn, forkserver): receive `dest_queues_dict`
  as a serialised parameter at process start. Separate memory means any
  mutation of `client_queues_destination` in the parent process is invisible to
  the running child. There is no mechanism to update the destination list in a
  running publisher process short of IPC (Manager proxy, shared memory, or a
  signal). Stop-and-restart is the only approach that is both correct and simple.

- **Thread-based publishers**: `dest_queues_dict` is the same object as
  `self.client_queues_destination` (passed by reference, single process). In
  principle a thread would see additions, but `dict.items()` in Python 3 is a
  live view — adding to the dict mid-iteration raises
  `RuntimeError: dictionary changed size during iteration`. Snapshotting
  (`list(dest_queues_dict.items())`) at the start of each loop iteration would
  make mutation safe, but it creates an "eventual consistency" window: a message
  already dequeued from the source in the current iteration would be distributed
  without the new destination. That violates the stated invariant. For threads,
  restart is also cheap (no process-creation overhead), so avoiding it buys
  little.

**Why alternatives are worse:**

- **`Manager().dict()`**: Works across processes, but adds a Manager daemon
  process per `QueueLink` (or a shared one), and every `dest_queue.put()` in
  the distribution loop becomes a proxy IPC call. Measurable per-message
  overhead for what is typically a startup-time configuration step.
- **Reload signal (sentinel in the source queue)**: Requires publishers to
  recognise and act on an out-of-band signal mid-stream, complicating the
  publisher loop and making ordering guarantees harder to reason about.
- **Lock-protected snapshot** (threads only): Would require passing
  `queues_lock` into the `@staticmethod` publisher, and holding the lock
  across `dest_queue.put()` calls risks a deadlock if any destination queue
  is full and blocks.

**Current status**: The stop-and-restart approach is correct for the stated
consistency requirement. The O(n) cost is only meaningful when all three of
the following are true simultaneously: many source queues, process-based start
method (spawn/forkserver), and destinations added frequently at runtime. The
typical use case — few sources, destinations configured at startup — makes the
cost negligible.

The `register_queue()` docstring explains the mechanism and cost. Tests covering
dynamic registration (adding a destination after start, verifying no-loss
delivery to all destinations, multiple-source O(n) restart) were added to
`tests/tests/queuelink_test.py` (`QueueLinkDynamicDestinationTest`,
`QueueLinkDynamicDestinationSpawnTest`).

---

### 4. `Metrics.new_id()` duplicates `common.new_id()` (metrics.py:121–127) ✅ Resolved (FEAT-002)

Identical 6-char hex ID generation logic exists in `common.py` (`new_id()`),
`_QueueHandleAdapterBase.__init__`, and `Metrics.new_id()`. There is a single
authoritative version in `common.py`. The others should call it.

---

### 5. `ExceptionHandler` is a class that inherits from `Exception` (exceptionhandler.py)

`ExceptionHandler` is not an exception type itself — it is a logging wrapper
that happens to inherit `Exception`. It logs details to the module logger and
builds a formatted string, but is never *raised* in the codebase (it is
instantiated and discarded). This is confusing: it looks like a base class for
custom exceptions, but it is actually a utility called for side effects.

Consider either: (a) making it a plain function `log_exception(error, message)`
that does the formatting/logging without inheriting `Exception`, or (b)
documenting clearly that it is a logging utility, not an exception type.

---

### 6. `QueueLink.is_alive()` raises `ProcessNotStarted` on first call (queuelink.py) ✅ Resolved (FEAT-004)

The method raises `ProcessNotStarted` if `started` is not set, rather than
returning `False`. This forces callers to handle an exception for a condition
that is a normal state (nothing registered yet). A bool return of `False`
before any publishers are started would be more consistent with Python
conventions for `is_alive()` checks.

---

## Consistency Issues

### 7. Three different encoding strategies for handles

| Location | Approach |
|---|---|
| `QueueHandleAdapterReader.__init__` | `codecs.getreader('utf-8')` wrapping |
| `QueueHandleAdapterWriter.queue_handle_adapter` | `content.encode('utf-8')` / `content.decode('utf-8')` inline |
| `writeout.py` | `kitchenpatch.getwriter('utf-8')` |
| `contentwrapper.py` | `kitchenpatch.getwriter/getreader` |

The reliance on `kitchenpatch` (a non-standard library) in two modules while
`codecs` (stdlib) is used in another creates an inconsistency. If `kitchenpatch`
is required for a specific reason (e.g., handling surrogate characters in bytes
streams that `codecs` mishandles), that reason should be documented. If not, the
encoding strategy should be unified.

---

### 8. Writer adapter binary mode detection is fragile (queue_handle_adapter_writer.py)

When a path string or `PathLike` is passed as the `handle`, the writer lazily
opens it on the first line it dequeues, choosing binary or text mode based on
whether that first line has a `decode` attribute:

```python
def open_location(location, line):
    if hasattr(line, 'decode'):   # bytes → binary mode
        return open(location, mode='w+b')
    return open(location, mode='w+')  # str → text mode
```

FEAT-006 added `TypeError` guards so that if a later line's type disagrees with
the mode chosen by the first line, the worker raises immediately rather than
silently corrupting the file:

```python
if is_handle_bin and not is_content_bin:
    raise TypeError(
        'Handle opened in binary mode (set by first line) but subsequent '
        'line is str. All lines must be the same type.')
if not is_handle_bin and is_content_bin:
    raise TypeError(
        'Handle opened in text mode (set by first line) but subsequent '
        'line is bytes. All lines must be the same type.')
```

This is an improvement over silent failure, but several concerns remain:

**1. Terminal, unrecoverable failure.** The `TypeError` propagates out of the
`while True` loop entirely and is not caught anywhere in the adapter. The worker
process or thread dies without draining the queue or signalling the caller. Any
items already in the queue are lost. There is no way for the caller to catch or
handle this condition short of watching for the adapter to stop unexpectedly.

**2. Non-deterministic failure under concurrent producers.** If multiple
producers write to the same queue with different types (e.g., one subprocess
yields `bytes`, another yields `str`), the outcome — which mode gets selected,
and whether a `TypeError` occurs — depends on which line arrives first. This is
a race-sensitive invariant with no caller-visible way to enforce it up front.

**3. No pre-declaration of intended mode.** The `handle` parameter accepts a
path but there is no `mode` parameter. A caller who knows in advance whether
the stream will be binary or text has no way to communicate that, and cannot
prevent the lazy-open logic from inferring incorrectly if the first line is
atypical (e.g., a short `bytes` header on an otherwise text stream).

**4. `.mode` attribute assumed on all handles.** When `handle` is an
already-open file object rather than a path, the code reads `'b' in handle.mode`
to decide whether it is binary. Not all `io`-compatible objects expose `.mode`
(notably `io.BytesIO`, `io.StringIO`, and some custom wrappers do not). An
`AttributeError` here would also kill the worker without a clear error message.

**`.mode` re-read timing.** `is_handle_bin` is currently set on every loop
iteration at line 146 (`is_handle_bin = 'b' in handle.mode`). File mode is
immutable once opened, so re-reading it every iteration is pure overhead.
More importantly, `handle` is a local variable inside a single-worker process
or thread and is never shared — so repeated reads are not a race condition per
se — but the check does depend on `.mode` being present on the object. If a
pre-opened handle lacks `.mode`, the `AttributeError` surfaces on the first
line processed rather than at construction time, making the failure harder to
diagnose. Moving the check to exactly where the handle becomes ready
(once, at the right moment) eliminates both the repeated lookup and the
deferred-discovery problem:

- For pre-opened handles: `is_handle_bin` can be determined before the loop,
  right after the `if isinstance(handle, get_args(UNION_SUPPORTED_PATH_TYPES))`
  block confirms the handle is already open.
- For lazy-opened handles: `is_handle_bin` should be set immediately after
  `handle = open_location(handle_name, line)` returns, before the type-guard
  checks below it.

In both cases `is_handle_bin` transitions from `None` to a `bool` exactly
once per worker execution and is never re-read from the handle object.

**Preferred fix — thorough approach:**

1. **Replace `.mode` sniffing with `isinstance` checks.** Use
   `isinstance(handle, (io.RawIOBase, io.BufferedIOBase))` to detect binary
   handles. This works for all standard `io` types — `io.BufferedWriter`
   (returned by `open(..., 'wb')`), `io.BytesIO`, etc. — and raises nothing
   for objects that lack `.mode`. `io.TextIOBase` (including `io.TextIOWrapper`
   and `io.StringIO`) covers the text side. These checks do not require
   accessing any mutable state on the handle object.

2. **Set `is_handle_bin` once, at the moment the handle becomes ready.**
   For pre-opened handles, before the loop. For lazy-opened handles, immediately
   after `open_location()` returns. Remove the `is_handle_bin = 'b' in handle.mode`
   line from the loop body entirely.

3. **Add a `mode` parameter to `QueueHandleAdapterWriter.__init__`** (and
   thread it through to `queue_handle_adapter` and `open_location`) so callers
   who know their stream type can declare it explicitly. When `mode` is
   supplied, `open_location` uses it directly; when absent, the isinstance-
   based inference is the fallback. This eliminates the non-deterministic
   first-line dependency for path-based handles.

4. **Catch `TypeError` inside the loop, log it with the offending line's type
   and the handle's expected mode, set the stop event, and `break` cleanly.**
   Let the worker drain gracefully rather than dying with an unhandled
   exception. The caller can detect the unexpected stop via `is_alive()`.

5. **Add explicit tests** for: (a) a pre-opened `io.BytesIO` handle without
   `.mode`, (b) a mixed-type stream that should hit the `TypeError` path and
   stop cleanly, and (c) a path-based handle with an explicit `mode` argument.

---

### 9. `link_timeout` default inconsistency between `QueueLink` and `_publisher` ✅ Resolved (FEAT-005)

`QueueLink.__init__` defaults `link_timeout=0.01`, but the publisher uses it as
`safe_get(source_queue, timeout=link_timeout)` where the `AGENTS.md` note says
"default 0.1 seconds". The actual code default is 0.01 seconds. The
documentation is stale — one place says 0.1, another says 0.01.

---

## Performance Observations

### 10. `safe_get()` polling for SimpleQueue has variable latency ✅ Resolved (FEAT-005)

For `SimpleQueue` types, `safe_get()` falls into a polling loop with 0.005-second
sleep cycles. On a lightly loaded system this adds up to 5ms latency per item.
Under high throughput (thousands of items/second) this becomes the bottleneck.
The constraint is real — `SimpleQueue.get()` has no timeout parameter — but the
trade-off should be documented at the `QUEUE_TYPE_LIST` level in `common.py` so
users selecting SimpleQueue understand the cost.

---

### 11. Metrics collection can stall publishers under load ✅ Resolved (FEAT-002)

The publisher emits metrics by calling `metrics_queue.put()` in its main loop.
If the metrics consumer falls behind and the queue fills, the publisher blocks on
`put()`. The `LimitedLengthQueue` wrapper mitigates this by capping size at 100
and draining, but draining is itself a blocking operation. For high-throughput
publishers, metrics should be fire-and-forget (non-blocking `put_nowait` with
discard-on-full) rather than blocking.

---

## Structural Observations

### 12. `classtemplate.py` naming

The file is named `classtemplate.py` and the class is `ClassTemplate`. This is
accurate but generic. The class is specifically a *logging mixin*, and
downstream maintainers (or agents) might not realize its purpose from the name
alone. Consider renaming to `logging_mixin.py` / `LoggingMixin` in a future
refactor. Not urgent; note it when touching that file.

---

### 13. `throughput.py` and `throughput_results.py` live in `src/queuelink/`

These are benchmarking utilities, not part of the public library API. Their
presence in `src/queuelink/` means they are packaged and installed with the
library. `throughput_results.py` even creates a SQLite database at a hardcoded
relative path (`throughput/throughput.sqlite.db`). Consider whether these should
live in a `benchmarks/` or `tools/` directory at the repo root, or be excluded
from the package manifest via `[options.packages.find]` in `setup.cfg`.

---

### 14. `contentwrapper.py` descriptor protocol usage is undocumented ✅ Resolved (FEAT-005)

`ContentWrapper` intercepts attribute access on `.value` using `__getattr__` and
`__setattr__`. This is non-obvious Python — a reader who does not know the
descriptor protocol may not understand why `obj.value = data` can trigger file
I/O. A brief comment in the class docstring explaining "this class uses
`__setattr__`/`__getattr__` to intercept `.value` access for transparent
disk buffering" would prevent future maintainers from accidentally breaking the
invariant.

---

### 15. `link.py` stub broken import ✅ RESOLVED

Resolved by FEAT-001. `link()` is fully implemented.

---

## Prioritization Summary

| # | Area | Severity | Effort | Status |
|---|---|---|---|---|
| 1 | `data_points` class attribute bug | **High** (correctness) | Low | ✅ Resolved (FEAT-002) |
| 2 | `get_all_data()` key collision bug | **High** (correctness) | Low | ✅ Resolved (FEAT-002) |
| 3 | Destination change restarts all publishers | Medium (performance) | High | ✅ Closed — design validated, documented, tested (2026-04-19) |
| 4 | Duplicate `new_id()` | Low (cleanliness) | Low | ✅ Resolved (FEAT-002) |
| 5 | `ExceptionHandler` naming confusion | Low (clarity) | Low | Open |
| 6 | `is_alive()` raises instead of returning False | Low (API consistency) | Low | ✅ Resolved (FEAT-004) |
| 7 | Encoding strategy inconsistency | Medium (correctness risk) | Medium | Open — deferred (documented) |
| 8 | Binary mode detection fragility | Medium (correctness risk) | Low | Open — untracked |
| 9 | `link_timeout` doc/code mismatch | Low (docs) | Low | ✅ Resolved (FEAT-005) |
| 10 | SimpleQueue polling latency undocumented | Low (docs) | Low | ✅ Resolved (FEAT-005) |
| 11 | Metrics can stall publishers | Medium (reliability) | Medium | ✅ Resolved (FEAT-002) |
| 12 | `ClassTemplate` naming | Low (clarity) | Low | Open — deferred (rename when touching) |
| 13 | Benchmarking code in package | Low (packaging) | Low | ✅ Resolved (FEAT-003) |
| 14 | `ContentWrapper` descriptor pattern undocumented | Low (maintainability) | Low | ✅ Resolved (FEAT-005) |
| 15 | Broken import in `link.py` stub | Medium (correctness) | Low | ✅ Resolved (FEAT-001) |
