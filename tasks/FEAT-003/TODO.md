# FEAT-003 Task Board

Phases must complete in order. Do not start Phase N+1 until all Phase N tasks are DONE.

## Phase 1 — Relocation

| ID | Task | Status | Files |
|----|------|--------|-------|
| 003-1-1 | Create `benchmarks/` with `__init__.py` and `context.py` | NOT_STARTED | benchmarks/__init__.py, benchmarks/context.py |
| 003-1-2 | Copy `tests/content/line_output.py` → `benchmarks/content/line_output.py` | NOT_STARTED | benchmarks/content/line_output.py |
| 003-1-3 | Move `throughput_results.py` to `benchmarks/`; update imports | NOT_STARTED | benchmarks/throughput_results.py, src/queuelink/throughput_results.py |
| 003-1-4 | Move `throughput.py` to `benchmarks/`; fix intra-benchmark import | NOT_STARTED | benchmarks/throughput.py, src/queuelink/throughput.py |
| 003-1-5 | Move `queuelink_throughput_test_exclude.py` to `benchmarks/`; fix imports | NOT_STARTED | benchmarks/throughput_test_exclude.py, tests/tests/queuelink_throughput_test_exclude.py |
| 003-1-6 | Verify `tox -e pylint` and `tox -e bandit` pass after removal | NOT_STARTED | — |

## Phase 2 — Fix `throughput_results.py` bugs + host context

| ID | Task | Status | Files |
|----|------|--------|-------|
| 003-2-1 | Fix table creation SQL (replace `?` placeholder with f-string) | NOT_STARTED | benchmarks/throughput_results.py |
| 003-2-2 | Fix INSERT parentheses (`VALUES (?, ?, ?)`) | NOT_STARTED | benchmarks/throughput_results.py |
| 003-2-3 | Fix `get_latest_session_id()` len() bug | NOT_STARTED | benchmarks/throughput_results.py |
| 003-2-4 | Make DB path configurable; auto-create parent directory | NOT_STARTED | benchmarks/throughput_results.py, benchmarks/throughput.py |
| 003-2-5 | Add `host_info` table: hostname, cpu_model, cpu_count, python_version, os_platform | NOT_STARTED | benchmarks/throughput_results.py |

## Phase 3 — Fix `throughput.py` bugs

| ID | Task | Status | Files |
|----|------|--------|-------|
| 003-3-1 | Fix `content_dir` path (now points to `benchmarks/content/`) | NOT_STARTED | benchmarks/throughput.py |
| 003-3-2 | Fix `queue_link.close()` coverage in `elements_per_second_queuelink` | NOT_STARTED | benchmarks/throughput.py |
| 003-3-3 | Fix `QUEUE_TYPE_LIST` used as type annotation → `UNION_SUPPORTED_QUEUES` | NOT_STARTED | benchmarks/throughput.py |

## Phase 4 — Handle-adapter benchmarks

| ID | Task | Status | Files |
|----|------|--------|-------|
| 003-4-1 | Add `Throughput_QueueHandleAdapterReader` class | NOT_STARTED | benchmarks/throughput.py |
| 003-4-2 | Add `Throughput_QueueHandleAdapterWriter` class | NOT_STARTED | benchmarks/throughput.py |
| 003-4-3 | Add reader and writer test cases to `throughput_test_exclude.py` | NOT_STARTED | benchmarks/throughput_test_exclude.py |

## Phase 5 — Verify

| ID | Task | Status | Files |
|----|------|--------|-------|
| 003-5-1 | `tox -e pylint` and `tox -e bandit` pass (no src/ regressions) | NOT_STARTED | — |
| 003-5-2 | Manual smoke test: run one queue type / start method end-to-end; verify host_info row written | NOT_STARTED | — |
| 003-5-3 | Verify `throughput_results.py __main__` prints results correctly | NOT_STARTED | benchmarks/throughput_results.py |

## Phase 6 — Runner documentation

| ID | Task | Status | Files |
|----|------|--------|-------|
| 003-6-1 | Create `benchmarks/README.md`: when to run, how to interpret, host context, best practices | NOT_STARTED | benchmarks/README.md |
| 003-6-2 | Add one-line pointer to `benchmarks/README.md` from top-level `README.rst` | NOT_STARTED | README.rst |
