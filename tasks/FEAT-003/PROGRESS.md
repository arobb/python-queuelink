# FEAT-003: Fix or Rebuild Throughput System — Progress

## Status: DONE

See `TODO.md` for the full task list.

## Phase 1 — Relocation
- [x] 003-1-1: Create `benchmarks/` with `__init__.py` and `context.py`
- [x] 003-1-2: Copy `line_output.py` to `benchmarks/content/`
- [x] 003-1-3: Move `throughput_results.py` to `benchmarks/`
- [x] 003-1-4: Move `throughput.py` to `benchmarks/`
- [x] 003-1-5: Move `queuelink_throughput_test_exclude.py` to `benchmarks/`
- [x] 003-1-6: Verify lint/security scan passes

## Phase 2 — Fix `throughput_results.py` bugs + host context
- [x] 003-2-1: Fix table creation SQL (f-string with # nosec instead of ? placeholder)
- [x] 003-2-2: Fix INSERT parentheses (`VALUES (?, ?, ?)`)
- [x] 003-2-3: Fix `get_latest_session_id()` len() bug (`if results is not None`)
- [x] 003-2-4: Make DB path configurable (db_path parameter, auto-create directory)
- [x] 003-2-5: Add `host_info` table (hostname, cpu_model, cpu_count, python_version, os_platform)

## Phase 3 — Fix `throughput.py` bugs
- [x] 003-3-1: Fix `content_dir` path (now points to `benchmarks/content/`)
- [x] 003-3-2: Fix `queue_link.close()` coverage (try/finally)
- [x] 003-3-3: Fix `QUEUE_TYPE_LIST` type annotation → `UNION_SUPPORTED_QUEUES`

## Phase 4 — Handle-adapter benchmarks
- [x] 003-4-1: `Throughput_QueueHandleAdapterReader` class added
- [x] 003-4-2: `Throughput_QueueHandleAdapterWriter` class added
- [x] 003-4-3: Test cases in `throughput_test_exclude.py` added

## Phase 5 — Verify
- [x] 003-5-1: `tox -e pylint` and `tox -e bandit` pass (no src/ regressions; score 9.88/10 +0.00)
- [ ] 003-5-2: Manual smoke test (verify host_info row written) — skipped per task instructions (benchmarks are slow)
- [ ] 003-5-3: `__main__` results output verified — skipped per task instructions

## Phase 6 — Runner documentation
- [x] 003-6-1: Create `benchmarks/README.md`
- [x] 003-6-2: Add pointer from `README.rst` (Performance section)
