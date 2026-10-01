# FEAT-010 Task Board

Phases must complete in order. Do not start Phase N+1 until all Phase N tasks are DONE.

## Phase 1 — Small fixes

| ID | Task | Status | Files |
|----|------|--------|-------|
| 010-1-1 | Writer `flush()`: tolerate `EINVAL`/`ENOTSUP` from `os.fsync` on pipes | DONE | src/queuelink/queue_handle_adapter_writer.py |
| 010-1-2 | Normalize int queue IDs to `str` in `get_queue`, `is_empty`; guard `unregister_queue(FROM)` against unknown IDs | DONE | src/queuelink/queuelink.py |
| 010-1-3 | `close()`: `started.is_set()` instead of Event truthiness (QueueLink + adapter base) | DONE | src/queuelink/queuelink.py, src/queuelink/queue_handle_adapter_base.py |
| 010-1-4 | `_publisher`: emit final metrics and `return` on `EOFError` | DONE | src/queuelink/queuelink.py |
| 010-1-5 | `validate_direction`: consistent str handling across versions; `ValueError` with accurate message (per Q1) | DONE | src/queuelink/queuelink.py |

## Phase 2 — Publisher wait/shutdown strategy

| ID | Task | Status | Files |
|----|------|--------|-------|
| 010-2-1 | Add `_put_until_stopped` helper; use for every destination put in `_publisher` | DONE | src/queuelink/queuelink.py |
| 010-2-2 | Implement partial-fan-out-on-stop semantics (per Q2); call `task_done()` only after delivery/abandon decision | DONE | src/queuelink/queuelink.py |
| 010-2-3 | Benchmark current idle CPU and stop latency (baseline) with `benchmarks/` | DONE | benchmarks/ |
| 010-2-4 | Raise default `link_timeout` (per Q3); re-run benchmark and record results in PROGRESS.md | DONE | src/queuelink/queuelink.py, src/queuelink/link.py |
| 010-2-5 | (Optional, per Q4) `connection.wait` path for `multiprocessing.SimpleQueue` with polling fallback | DEFERRED — see DECISIONS.md Q4 | src/queuelink/common.py |
| 010-2-6 | Correct `safe_get` docstring (only `multiprocessing.SimpleQueue` polls) | DONE | src/queuelink/common.py |
| 010-2-7 | Record the no-sentinel decision in DECISIONS.md | DONE | tasks/FEAT-010/DECISIONS.md |
| 010-2-8 | Fix Q5: `cancel_join_thread()` on `multiprocessing.Queue`/`JoinableQueue` destinations at every `_publisher` exit point, so an unbounded unread destination's feeder thread can't hang process exit | DONE (bounded flush first, then `cancel_join_thread()`; process publishers only; see PROGRESS.md) | src/queuelink/queuelink.py, tests/tests/queuelink_test.py |

## Phase 3 — Regression tests

| ID | Task | Status | Files |
|----|------|--------|-------|
| 010-3-1 | Full-destination stop test (thread + each process start method); `register_queue(TO)` on blocked link returns | DONE | tests/tests/queuelink_test.py |
| 010-3-2 | Writer-to-subprocess-stdin test; assert no thread exception | DONE | tests/tests/queuelink_handle_adapter_writer_test.py |
| 010-3-3 | Int ID tests for `get_queue` / `is_empty` | DONE | tests/tests/queuelink_test.py |
| 010-3-4 | EOFError-destination exit test | DONE | tests/tests/queuelink_test.py |
| 010-3-5 | Direction-as-str test with identical outcome on all versions | DONE | tests/tests/queuelink_test.py |
| 010-3-6 | `queue.SimpleQueue` uses `get(timeout=)` path (no polling) | DONE | tests/tests/queuelink_safe_get_test.py |

## Phase 4 — Docs reconciliation

| ID | Task | Status | Files |
|----|------|--------|-------|
| 010-4-1 | README "Tuning link_timeout": new default; clarify timeout ≠ message latency | DONE | README.rst |
| 010-4-2 | CHANGELOG Unreleased: Fixed (items 1–6), Changed (`link_timeout` default) | DONE | CHANGELOG.rst |
| 010-4-3 | Mark REVIEW-002 items 1–6, 22 resolved | NOT_STARTED | tasks/REVIEW-002.md |
