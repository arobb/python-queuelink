# Task Board

All work is registered here. Features appear as a single row with detail in `tasks/FEAT-NNN/`.

## Active Features

| ID       | Title                                    | Status      | Owner           | Updated    | Files                                                                                                              |
|----------|------------------------------------------|-------------|-----------------|------------|--------------------------------------------------------------------------------------------------------------------|
| FEAT-001 | link() factory function                  | DONE        | session-current | 2026-03-22 | src/queuelink/link.py, tests/tests/link_test.py, README.rst, docs/*.rst                                            |
| FEAT-002 | Fix or rebuild metrics system            | DONE        | session-prior   | 2026-03-25 | src/queuelink/metrics.py, src/queuelink/queuelink.py, tests/tests/metrics_test.py                                  |
| FEAT-003 | Fix or rebuild throughput system         | NOT_STARTED | None            | 2026-03-26 | benchmarks/throughput.py, benchmarks/throughput_results.py, benchmarks/throughput_test_exclude.py                  |
| FEAT-004 | API and exception handler polish         | NOT_STARTED | None            | 2026-03-26 | src/queuelink/exceptionhandler.py, src/queuelink/queuelink.py                                                      |
| FEAT-005 | Documentation and naming clarity         | NOT_STARTED | None            | 2026-03-26 | src/queuelink/common.py, src/queuelink/queuelink.py, docs/*.rst                                                    |
| FEAT-006 | Encoding strategy consistency            | NOT_STARTED | None            | 2026-03-26 | src/queuelink/queue_handle_adapter_reader.py, src/queuelink/queue_handle_adapter_writer.py, src/queuelink/writeout.py, src/queuelink/contentwrapper.py |
| FEAT-007 | Publisher restart on new destination     | NOT_STARTED | None            | 2026-03-26 | src/queuelink/queuelink.py                                                                                         |
| FEAT-008 | Windows support                          | NOT_STARTED | None            | 2026-03-26 | src/queuelink/common.py, setup.cfg, .github/workflows/ci.yaml                                                      |


## Phases

See `tasks/FEAT-NNN/TODO.md` for phase breakdowns and individual tasks.

## Open Reviews

| ID | Title | Date | Open Items |
|----|-------|------|------------|
| REVIEW-001 | Architectural review — full source read | 2026-03-22 | 9 open (items 1, 2, 4, 11 resolved by FEAT-002; item 13 in-progress FEAT-003; item 15 resolved by FEAT-001) |

## Notes

- FEAT-001: All implementation and documentation complete (v1). v2 auto-wrap/unwrap tracked in PROGRESS.md.
- FEAT-002: Complete. All 7 phases done; merged 2026-03-25 (commit 4f5dbf5).
- FEAT-003: Plan and decisions finalized (tasks/FEAT-003/PLAN.md). Relocate to benchmarks/, fix SQLite bugs, add handle-adapter benchmarks.
- FEAT-004: Triage of REVIEW-001 items 5, 6. ExceptionHandler rename + is_alive() return-False fix.
- FEAT-005: Triage of REVIEW-001 items 9, 10, 12, 14. Doc/comment/naming fixes only.
- FEAT-006: Triage of REVIEW-001 items 7, 8. Encoding strategy unification across adapters.
- FEAT-007: Triage of REVIEW-001 item 3. High-effort design work; needs scoping before start.
- FEAT-008: Windows support. Blocked on Phase 1 audit (kitchen/kitchenpatch Windows compat). May depend on FEAT-006 landing first. Plan in tasks/FEAT-008/PLAN.md.
- REVIEW-001 items 3, 5–10, 12, 14 triaged into FEAT-004 through FEAT-007 above.
