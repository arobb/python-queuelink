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

The root cause is that publishers receive the destination dict at start time
rather than holding a shared reference to a live dict.

**Options (in increasing complexity)**:
- **Shared proxy dict**: Pass a `Manager().dict()` as the destination container
  so publishers see updates without restart. Trade-off: Manager dependency and
  proxy overhead on every `put()`.
- **Reload signal**: Send a sentinel into the source queue that tells the
  publisher to re-read destinations from a shared structure.
- **Accept current behaviour, document it**: For the typical case (few sources,
  destinations configured at startup), the restart cost is negligible. Document
  the O(n) restart cost explicitly in the docstring and in AGENTS.md.

The simplest defensible path is the third: document the behaviour. Changing it
is a meaningful refactor that should be its own tracked item.

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

### 6. `QueueLink.is_alive()` raises `ProcessNotStarted` on first call (queuelink.py)

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

The writer opens a file handle in binary or text mode based on the encoding of
the *first* line it processes:

```python
def open_location(location, line):
    if hasattr(line, 'decode'):   # bytes
        return open(location, mode='w+b')
    return open(location, mode='w+')
```

If a mixed-encoding stream is written (e.g., text first, then bytes), the mode
is locked by the first line. A later binary line written to a text-mode file
would cause a `TypeError`. This edge case is not documented or guarded.

---

### 9. `link_timeout` default inconsistency between `QueueLink` and `_publisher`

`QueueLink.__init__` defaults `link_timeout=0.01`, but the publisher uses it as
`safe_get(source_queue, timeout=link_timeout)` where the `AGENTS.md` note says
"default 0.1 seconds". The actual code default is 0.01 seconds. The
documentation is stale — one place says 0.1, another says 0.01.

---

## Performance Observations

### 10. `safe_get()` polling for SimpleQueue has variable latency

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

### 14. `contentwrapper.py` descriptor protocol usage is undocumented

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
| 3 | Destination change restarts all publishers | Medium (performance) | High | Open |
| 4 | Duplicate `new_id()` | Low (cleanliness) | Low | ✅ Resolved (FEAT-002) |
| 5 | `ExceptionHandler` naming confusion | Low (clarity) | Low | Open |
| 6 | `is_alive()` raises instead of returning False | Low (API consistency) | Low | Open |
| 7 | Encoding strategy inconsistency | Medium (correctness risk) | Medium | Open |
| 8 | Binary mode detection fragility | Medium (correctness risk) | Low | Open |
| 9 | `link_timeout` doc/code mismatch | Low (docs) | Low | Open |
| 10 | SimpleQueue polling latency undocumented | Low (docs) | Low | Open |
| 11 | Metrics can stall publishers | Medium (reliability) | Medium | ✅ Resolved (FEAT-002) |
| 12 | `ClassTemplate` naming | Low (clarity) | Low | Open |
| 13 | Benchmarking code in package | Low (packaging) | Low | Open |
| 14 | `ContentWrapper` descriptor pattern undocumented | Low (maintainability) | Low | Open |
| 15 | Broken import in `link.py` stub | Medium (correctness) | Low | ✅ Resolved (FEAT-001) |
