# Task Board

All work is registered here. Features appear as a single row with detail in `tasks/FEAT-NNN/`.

## Active Features

| ID       | Title                            | Status      | Owner           | Updated | Files                                                                                                              |
|----------|----------------------------------|-------------|-----------------|---------|--------------------------------------------------------------------------------------------------------------------|
| FEAT-001 | link() factory function          | IN_PROGRESS | session-current | 2026-03-22 | src/queuelink/link.py, tests/tests/link_test.py, README.rst, docs/*.rst                                            |
| FEAT-002 | Fix or rebuild metrics system    | DONE        | session-current | 2026-03-25 | src/queuelink/metrics.py, src/queuelink/queuelink.py, tests/tests/metrics_test.py, tests/tests/queuelink_test.py  |
| FEAT-003 | Fix or rebuild throughput system | NOT_STARTED | None            | 2026-03-22 | src/queuelink/throughput.py, src/queuelink/throughput_results.py, tests/tests/queuelink_throughput_test_exclude.py |


## Phases

See `tasks/FEAT-001/TODO.md` for phase breakdown and individual tasks.

## Open Reviews

| ID | Title | Date | Open Items |
|----|-------|------|------------|
| REVIEW-001 | Architectural review — full source read | 2026-03-22 | 10 open (items 1, 2, 4, 11 resolved by FEAT-002; item 15 resolved by FEAT-001) |

## Notes

- FEAT-001: Core implementation complete (v1). Documentation updates pending (steps 15-18 in PROGRESS.md).
- FEAT-002: Complete. Metrics bugs fixed, publisher-stall resolved, full test coverage added.
- FEAT-003: Needs to be scoped with human input.
- REVIEW-001 items 3, 5–10, 12–14 are pending triage into tasks/features.