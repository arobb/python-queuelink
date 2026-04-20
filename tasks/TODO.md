# Task Board

All work is registered here. Features appear as a single row with detail in `tasks/FEAT-NNN/`.

## Active Features

| ID       | Title                                    | Status      | Owner           | Updated    | Files                                                                                                              |
|----------|------------------------------------------|-------------|-----------------|------------|--------------------------------------------------------------------------------------------------------------------|
| FEAT-001 | link() factory function                  | DONE        | session-current | 2026-03-22 | src/queuelink/link.py, tests/tests/link_test.py, README.rst, docs/*.rst                                            |
| FEAT-002 | Fix or rebuild metrics system            | DONE        | session-prior   | 2026-03-25 | src/queuelink/metrics.py, src/queuelink/queuelink.py, tests/tests/metrics_test.py                                  |
| FEAT-003 | Fix or rebuild throughput system         | DONE        | session-2026-03-27 | 2026-03-27 | benchmarks/throughput.py, benchmarks/throughput_results.py, benchmarks/throughput_test_exclude.py                  |
| FEAT-004 | API and exception handler polish         | DONE        | session-2026-04-05 | 2026-04-05 | src/queuelink/exceptionhandler.py, src/queuelink/queuelink.py                                                      |
| FEAT-005 | Documentation and naming clarity         | DONE        | session-2026-03-27 | 2026-03-27 | src/queuelink/common.py, src/queuelink/queuelink.py, README.rst                                                    |
| FEAT-006 | Encoding strategy consistency            | DONE        | session-2026-03-27 | 2026-03-27 | src/queuelink/queue_handle_adapter_reader.py, src/queuelink/queue_handle_adapter_writer.py, src/queuelink/writeout.py, src/queuelink/contentwrapper.py |
| FEAT-007 | Publisher restart on new destination     | DONE        | session-2026-03-27 | 2026-03-27 | src/queuelink/queuelink.py                                                                                         |
| FEAT-008 | Windows support                          | NOT_STARTED | None            | 2026-03-26 | src/queuelink/common.py, setup.cfg, .github/workflows/ci.yaml                                                      |
| FEAT-009 | Writer adapter binary mode detection     | NOT_STARTED | None            | 2026-04-20 | src/queuelink/queue_handle_adapter_writer.py, tests/tests/queuelink_handle_adapter_writer_test.py                  |


## Phases

See `tasks/FEAT-NNN/TODO.md` for phase breakdowns and individual tasks.

## Open Reviews

| ID | Title | Date | Open Items |
|----|-------|------|------------|
| REVIEW-001 | Architectural review — full source read | 2026-03-22 | 5 open: item 3 (deferred, FEAT-007), item 5 (blocked), item 7 (deferred, FEAT-006), item 8 (untracked), item 12 (deferred) |

## Notes

- FEAT-001: All implementation and documentation complete (v1). v2 auto-wrap/unwrap tracked in PROGRESS.md.
- FEAT-002: Complete. All 7 phases done; merged 2026-03-25 (commit 4f5dbf5).
- FEAT-003: Done 2026-03-27. Relocated to benchmarks/, fixed 3 SQLite bugs, added host_info table, added adapter benchmark classes, added benchmarks/README.md.
- FEAT-004: Done 2026-04-05. ExceptionHandler refactored: log_exception() function added, writeout.py updated to log+reraise original; is_alive() fix done. Binary chunk test skips added for LifoQueue/PriorityQueue (non-FIFO ordering incompatible with chunk reassembly).
- FEAT-005: Done 2026-03-27. link_timeout doc fixed, SimpleQueue polling note added, ContentWrapper descriptor documented. ClassTemplate rename deferred.
- FEAT-006: Done 2026-03-27. Encoding rationale documented inline; defensive type check added to QueueHandleAdapterWriter.
- FEAT-007: Done 2026-03-27. Option A implemented — O(n) restart cost documented in register_queue() docstring.
- FEAT-008: Windows support. Blocked on Phase 1 audit (kitchen/kitchenpatch Windows compat). May depend on FEAT-006 landing first. Plan in tasks/FEAT-008/PLAN.md.
- REVIEW-001: items 1, 2, 4, 11 resolved by FEAT-002; item 13 by FEAT-003; item 15 by FEAT-001; item 6 by FEAT-004; items 9, 10, 14 by FEAT-005; item 3 design validated/documented/tested 2026-04-19; item 7 resolved by FEAT-006. Open: 5 (deprecated, removal deferred to v3 with FEAT-008), 8 (tracked as FEAT-009), 12 (deferred — rename when touching).
