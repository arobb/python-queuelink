# FEAT-002: Fix or Rebuild the Metrics System

## Context

The metrics system (`metrics.py`) has two correctness bugs, a publisher-stall risk, code
duplication, and zero test coverage. These issues affect any downstream consumer of
`QueueLink.get_metrics()` and could silently corrupt throughput measurements (FEAT-003).
The user is open to a redesign and confirmed thread safety, testing, and the
publisher-stall fix are all in scope.

## REVIEW-001 items addressed

| # | Issue | Disposition |
|---|-------|-------------|
| 1 | `data_points` mutable class attribute | Fix in Phase 1 |
| 2 | `get_all_data()` key collision | Fix in Phase 1 |
| 4 | Duplicate `new_id()` | Fix in Phase 1 |
| 11 | Metrics stall publishers | Fix in Phase 2 |

## Approach: moderate redesign

Keep `TimedMetric` and `CountMetric` as separate classes (genuinely different data).
Keep a slimmed-down `BaseMetric` for shared `__init__` logic and type annotation.
Keep `Metrics` manager (the publisher uses it as a facade).
Fix all bugs, add `to_dict()` to each metric class, add `MetricType` enum, and replace
blocking emission with fire-and-forget `put_nowait`.

---

## Phase 1 — Fix bugs and clean up `metrics.py`

**File: `src/queuelink/metrics.py`**

1. **Fix Bug 1**: Move `data_points`, `name`, `max_points` from class attributes to
   `__init__` on `BaseMetric`. Both `TimedMetric` and `CountMetric` call
   `super().__init__()` to get them as instance attributes.

2. **Fix Bug 2**: Change `get_all_data()` to return
   `{element_id: get_data(element_id)}` instead of the flattened dict-merge.

3. **Fix Item 4**: Remove `Metrics.new_id()`, import and use `common.new_id()`.

4. **Add `MetricType` enum** (`TIMING`, `COUNTING`) — replace string comparison in
   `add_element()`.

5. **Add `to_dict()`** on `TimedMetric` and `CountMetric` so each metric can serialize
   itself. Simplify `Metrics.get_data()` to call `element.to_dict()`.

## Phase 2 — Non-blocking metrics emission in publisher

**File: `src/queuelink/queuelink.py`**

1. Create `metrics_queue` with `maxsize=100` in `__init__` and `_stop_publisher`.

2. In `_publisher`: replace `LimitedLengthQueue` wrapping with direct
   `put_nowait` + `except Full: pass`. Remove `start_method` param from `_publisher`
   signature (only used for `LimitedLengthQueue`). Import `Full` from `queue`.

3. Update `_publisher` to use `MetricType` enum when calling `add_element()`.

4. `get_metrics()` behavior: keep drain-and-return-latest semantics (internal-only API).

## Phase 3 — Unit tests for metrics

**New file: `tests/tests/metrics_test.py`**

Focused unit tests (no matrix — metrics classes don't vary by queue type/start method):

- `TimedMetric` instance isolation (two instances don't share `data_points`)
- `start()` + `lap()` produce data points with correct statistics
- Rolling window caps at `max_points`
- `to_dict()` returns expected keys/types
- `CountMetric` instance isolation, `increment()`, `to_dict()`
- `Metrics.add_element()` with `MetricType` enum
- `Metrics.get_all_data()` returns dict keyed by element_id, no key collision
- Invalid metric type raises `ValueError`

## Phase 4 — Integration test for `get_metrics()` through QueueLink

**File: `tests/tests/queuelink_test.py`**

Add a focused test (not full matrix) that:
- Creates QueueLink with source + destination
- Pushes enough messages to trigger at least one periodic emission (>100)
- Calls `stop()` then `get_metrics()`
- Asserts returned dict is non-empty and contains timing/counting data with valid values

## Phase 5 — Update task board and REVIEW-001

- Mark items 1, 2, 4, 11 as resolved in REVIEW-001
- Update `tasks/TODO.md` status to IN_PROGRESS

---

## Files modified

| File | Type of change |
|------|---------------|
| `src/queuelink/metrics.py` | Bug fixes, enum, `to_dict()`, remove `new_id()` |
| `src/queuelink/queuelink.py` | `put_nowait`, `maxsize=100`, enum usage, remove `LimitedLengthQueue` from metrics path |
| `tests/tests/metrics_test.py` | New — unit tests |
| `tests/tests/queuelink_test.py` | Add integration test |
| `tasks/FEAT-002/*` | Plan/progress tracking |
| `tasks/TODO.md` | Status update |
| `tasks/REVIEW-001.md` | Mark resolved items |

## Out of scope

- Removing `LimitedLengthQueue` class itself (may have future uses)
- Throughput-specific measurement bugs (FEAT-003)
- `Metrics` class removal (facade is still useful for the publisher)

## Scoping decisions (from user)

1. Open to a larger redesign
2. Cross-cutting changes (publisher stall fix) are in scope
3. Thread safety in scope
4. `get_all_data()` is only used internally
5. The metrics system should be tested
6. Metrics supports throughput; throughput-specific bugs go to FEAT-003, but
   any metrics capabilities needed for correct throughput measurement are FEAT-002
