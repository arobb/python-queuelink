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
| FEAT-009 | Writer adapter binary mode detection     | DONE        | session-2026-04-20 | 2026-04-20 | src/queuelink/queue_handle_adapter_writer.py, tests/tests/queuelink_handle_adapter_writer_test.py                  |
| FEAT-010 | Core correctness fixes; publisher wait/shutdown | DONE | session-2026-09-29 (L0) | 2026-09-29 | src/queuelink/queuelink.py, src/queuelink/common.py, src/queuelink/link.py, src/queuelink/queue_handle_adapter_writer.py, src/queuelink/queue_handle_adapter_base.py, README.rst, docs/link_guide.rst, CHANGELOG.rst |
| FEAT-011 | ContentWrapper ownership, cleanup, fan-out | NOT_STARTED | None | 2026-09-28 | src/queuelink/contentwrapper.py, src/queuelink/queuelink.py, src/queuelink/queue_handle_adapter_reader.py, src/queuelink/link.py |
| FEAT-012 | Streaming spill for oversized lines (SpillWriter) | NOT_STARTED | None | 2026-09-28 | src/queuelink/contentwrapper.py, src/queuelink/queue_handle_adapter_reader.py |
| FEAT-013 | Reader overflow policy and durable spill | PROPOSED | None | 2026-09-28 | (proposal only — see PLAN.md) |
| FEAT-014 | Packaging, compatibility, housekeeping | NOT_STARTED | None | 2026-09-28 | pyproject.toml, setup.cfg, setup.py, requirements.txt, README.rst, .github/workflows/ci.yaml, src/queuelink/*.py |


## Phases

See `tasks/FEAT-NNN/TODO.md` for phase breakdowns and individual tasks.

## Open Reviews

| ID | Title | Date | Open Items |
|----|-------|------|------------|
| REVIEW-001 | Architectural review — full source read | 2026-03-22 | 2 open: item 5 (deprecated, removal deferred to v3 with FEAT-008), item 3 (deferred, O(n) cost documented/tested by FEAT-007) |
| REVIEW-002 | Correctness, ContentWrapper lifecycle, housekeeping | 2026-09-28 | FEAT-010 (1–6, 22, 24) ✅ resolved 2026-09-29. Remaining: FEAT-011 (7–14, 24), FEAT-012 (15), FEAT-013 (16, proposal), FEAT-014 (17–21, 23) |

## Notes

- FEAT-001: All implementation and documentation complete (v1). v2 auto-wrap/unwrap tracked in PROGRESS.md.
- FEAT-002: Complete. All 7 phases done; merged 2026-03-25 (commit 4f5dbf5).
- FEAT-003: Done 2026-03-27. Relocated to benchmarks/, fixed 3 SQLite bugs, added host_info table, added adapter benchmark classes, added benchmarks/README.md.
- FEAT-004: Done 2026-04-05. ExceptionHandler refactored: log_exception() function added, writeout.py updated to log+reraise original; is_alive() fix done. Binary chunk test skips added for LifoQueue/PriorityQueue (non-FIFO ordering incompatible with chunk reassembly).
- FEAT-005: Done 2026-03-27. link_timeout doc fixed, SimpleQueue polling note added, ContentWrapper descriptor documented. ClassTemplate rename deferred.
- FEAT-006: Done 2026-03-27. Encoding rationale documented inline; defensive type check added to QueueHandleAdapterWriter.
- FEAT-007: Done 2026-03-27. Option A implemented — O(n) restart cost documented in register_queue() docstring.
- FEAT-008: Windows support. Blocked on Phase 1 audit (kitchen/kitchenpatch Windows compat). May depend on FEAT-006 landing first. Plan in tasks/FEAT-008/PLAN.md.
- REVIEW-001: All 15 items closed. Items 1,2,4,11→FEAT-002; 13→FEAT-003; 15→FEAT-001; 6→FEAT-004; 9,10,14→FEAT-005; 3 documented/tested→FEAT-007; 7→FEAT-006; 8,12→FEAT-009. Item 5 deprecated (removal deferred to v3 with FEAT-008).
- FEAT-009: Done 2026-04-20. WriteMode enum, isinstance-based binary detection, _is_binary_handle() wrapper helper, log+reraise TypeError. classtemplate.py→logging_mixin.py (item 12) bundled.
- FEAT-010: Done 2026-09-29. Full-destination stop hang, writer fsync on pipes, int queue IDs, Event truthiness, EOFError busy-loop, direction str handling; put-side bounded wait + link_timeout default raised to 0.1s (no get-side sentinel, per DECISIONS.md). Also fixed, beyond original scope: an unbounded/unread multiprocessing.Queue destination could still hang process exit via its feeder thread (found during implementation, DECISIONS.md Q5) — bounded flush then cancel_join_thread(), process publishers only. 12 new regression tests, all independently re-verified by L0 (tox/pylint/bandit rerun, diffs read line-by-line). REVIEW-002 items 1–6, 22, 24 (FEAT-010 portion) marked resolved.
- FEAT-011: From REVIEW-002. Spilling stays opt-in. Copy-on-write .value, weakref.finalize cleanup, close()/context manager, spill_dir, clone-per-destination (hard link → copy fallback). Principle: bytes on disk never change once enqueued; one owner deletes each name.
- FEAT-012: From REVIEW-002. Previously untracked: readline() buffers oversized lines fully in memory. SpillWriter builder + seal(). Blocked on FEAT-011.
- FEAT-013: Proposal only (not scheduled). Overflow policy (block/drop_oldest/spill), SQLite-backed spill, Durability enum defaulting to NONE, at-least-once semantics.
- FEAT-014: From REVIEW-002. Zero runtime deps, pyproject-only packaging, drop 3.9 / add 3.14, Py2 remnants, README rationale, scaffolding location (do last).
