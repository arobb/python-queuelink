# FEAT-003: Fix or Rebuild Throughput System — Progress

## Status: NOT_STARTED

See `TODO.md` for the full task list.

## Phase 1 — Relocation
- [ ] 003-1-1: Create `benchmarks/` with `__init__.py` and `context.py`
- [ ] 003-1-2: Copy `line_output.py` to `benchmarks/content/`
- [ ] 003-1-3: Move `throughput_results.py` to `benchmarks/`
- [ ] 003-1-4: Move `throughput.py` to `benchmarks/`
- [ ] 003-1-5: Move `queuelink_throughput_test_exclude.py` to `benchmarks/`
- [ ] 003-1-6: Verify lint/security scan passes

## Phase 2 — Fix `throughput_results.py` bugs
- [ ] 003-2-1: Fix table creation SQL
- [ ] 003-2-2: Fix INSERT parentheses
- [ ] 003-2-3: Fix `get_latest_session_id()` len() bug
- [ ] 003-2-4: Make DB path configurable

## Phase 3 — Fix `throughput.py` bugs
- [ ] 003-3-1: Fix `content_dir` path
- [ ] 003-3-2: Fix `queue_link.close()` coverage
- [ ] 003-3-3: Fix `QUEUE_TYPE_LIST` type annotation

## Phase 4 — Handle-adapter benchmarks
- [ ] 003-4-1: `Throughput_QueueHandleAdapterReader`
- [ ] 003-4-2: `Throughput_QueueHandleAdapterWriter`
- [ ] 003-4-3: Test cases in `throughput_test_exclude.py`

## Phase 5 — Verify
- [ ] 003-5-1: `tox -e pylint` and `tox -e bandit` pass
- [ ] 003-5-2: Manual smoke test
- [ ] 003-5-3: `__main__` results output verified
