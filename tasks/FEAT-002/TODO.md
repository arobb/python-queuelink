# FEAT-002 Task Breakdown

## Phase 1 — Fix bugs and clean up metrics.py

- [x] 1.1 Move `data_points`/`name`/`max_points` to `BaseMetric.__init__` (fix Bug 1)
- [x] 1.2 Fix `get_all_data()` to key by element_id (fix Bug 2)
- [x] 1.3 Remove `Metrics.new_id()`, use `common.new_id()` (fix Item 4)
- [x] 1.4 Add `MetricType` enum; update `add_element()` to use it
- [x] 1.5 Add `to_dict()` to `TimedMetric` and `CountMetric`; simplify `get_data()`

## Phase 2 — Non-blocking metrics emission in queuelink.py

- [x] 2.1 Create bounded `metrics_queue` (maxsize=100); lazy process queue
- [x] 2.2 Replace `LimitedLengthQueue` in `_publisher` with `put_nowait` + evict-oldest
- [x] 2.3 Remove `start_method` param from `_publisher` (no longer needed)
- [x] 2.4 Update `_publisher` to use `MetricType` enum

## Phase 3 — Unit tests for metrics

- [x] 3.1 Create `tests/tests/metrics_test.py`
- [x] 3.2 `TimedMetric` instance isolation tests
- [x] 3.3 `TimedMetric` statistics correctness tests
- [x] 3.4 `CountMetric` tests
- [x] 3.5 `Metrics` manager tests (enum, get_all_data, key collision)

## Phase 4 — Integration test

- [x] 4.1 Add focused `get_metrics()` integration tests to `queuelink_test.py`
- [x] 4.2 Add process-publisher (spawn) integration test

## Phase 5 — Task board + REVIEW-001 updates

- [x] 5.1 Mark REVIEW-001 items 1, 2, 4, 11 as resolved
- [x] 5.2 Update `tasks/TODO.md` FEAT-002 status to DONE

## Phase 6 — Verification

- [x] 6.1 `tox -e py313` — 1749 passed
- [x] 6.2 `tox -e pylint` — clean
- [x] 6.3 `tox -e bandit` — clean
- [x] 6.4 Full matrix py39–py312 — all OK

## Phase 7 — Post-review fixes (2026-03-25)

- [x] 7.1 `_emit_metrics()`: evict oldest instead of drop newest
- [x] 7.2 `get_metrics()`: merge (`update`) not overwrite across queues
- [x] 7.3 `_metrics_queue_process`: lazy creation
- [x] 7.4 Restore `Dict[str, UNION_SUPPORTED_QUEUES]` type hint; clean up import alias
- [x] 7.5 `TimedMetric.start()`: delegate interval default to `Timer`
- [x] 7.6 `_update_mean()`: replace incremental formula with `statistics.mean()`
- [x] 7.7 `LimitedLengthQueue`: note as unused in docstring
- [x] 7.8 Add process-publisher spawn integration test
- [x] 7.9 Full matrix re-verification — all 5 versions clean
