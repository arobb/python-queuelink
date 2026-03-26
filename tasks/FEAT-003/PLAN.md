# FEAT-003: Fix or Rebuild Throughput System — Plan

**Status**: Draft — awaiting human scoping decisions (see Open Questions below)
**Files in scope**: `src/queuelink/throughput.py`, `src/queuelink/throughput_results.py`,
`tests/tests/queuelink_throughput_test_exclude.py`

---

## Summary of Known Issues

### Critical bugs (system is currently non-functional)

**`throughput_results.py`**

1. **Table creation is broken** (`__init__`, line 45): SQLite3 does not support
   parameterized table or column names. The current code attempts:
   ```python
   cursor.execute('CREATE TABLE IF NOT EXISTS ?(?)', (tbl, schema))
   ```
   This raises `sqlite3.OperationalError` at runtime. Table names must be
   interpolated directly (using f-strings, as the rest of the file already does
   with `# nosec` guards).

2. **INSERT missing parentheses** (`update_session_id`, line 69-70):
   ```python
   cursor.execute('INSERT INTO ... VALUES ?, ?, ?', (ppid, ...))
   ```
   SQLite requires `VALUES (?, ?, ?)`. The missing parentheses cause
   `sqlite3.OperationalError` on every write.

3. **`get_latest_session_id()` len() on wrong type** (line 118):
   ```python
   return results['session_id'] if len(results) > 0 else None
   ```
   `cursor.fetchone()` returns a single `sqlite3.Row` (or `None`), not a list.
   `len(results)` returns the column count, not a row count. Should be:
   ```python
   return results['session_id'] if results is not None else None
   ```

**`throughput.py`**

4. **`content_dir` path is wrong** (`Throughput.__init__`, line 97):
   ```python
   content_dir = os.path.join(os.path.dirname(__file__), '..', 'content')
   ```
   `__file__` is inside `src/queuelink/`. One level up is `src/`, which has no
   `content/` subdirectory. The content directory lives at `tests/content/`.
   However, this path is only used to locate `line_output.py` for handle-adapter
   benchmarks. No `Throughput_QueueLink` method actually uses
   `self.sample_command_path`, so this is a latent bug — it will only surface if
   handle-adapter throughput tests are added.

5. **Missing `queue_link.close()` in baseline path** (`elements_per_second_queuelink`):
   The method creates a `QueueLink` for the actual measurement and closes it, but
   the baseline test reads directly from `test_q` through the same QueueLink object
   without closing it on early exit paths (e.g., `ValueError` from
   `elements_per_seconds_increase`).

### Structural concern (REVIEW-001 item 13)

6. **Benchmarking code is packaged with the library**: `throughput.py` and
   `throughput_results.py` live in `src/queuelink/` and are installed as part of
   the `queuelink` package. `throughput_results.py` also creates a SQLite database
   at a hardcoded relative path (`throughput/throughput.sqlite.db`), which means the
   DB appears wherever the benchmark is run from.

---

## Open Questions (need human input before work begins)

These decisions affect scope and approach significantly:

**Q1 — Fix in place or relocate?**
- Option A (minimal): Fix the bugs in `src/queuelink/throughput*.py`. Keep the files
  where they are, accepting that they are packaged with the library.
- Option B (structural): Move benchmarking code to a `benchmarks/` directory at the
  repo root. Update `setup.cfg` to exclude it from the package. Update the test file
  to import from the new location. This addresses REVIEW-001 item 13.

**Q2 — Keep SQLite or simplify storage?**
- The SQLite approach is a reasonable design for structured benchmark data, but the
  implementation has fundamental SQL bugs and a hardcoded relative DB path.
- Option A: Fix the bugs and make the DB path configurable (e.g., via an env var or
  constructor argument defaulting to a user-writable location).
- Option B: Replace SQLite with a simpler format (CSV, JSON, or plain print-to-stdout)
  that is easier to maintain and inspect.

**Q3 — Scope boundary: handle-adapter benchmarks?**
- `throughput.py` has the scaffolding for handle-adapter tests (via `content_dir` /
  `sample_command_path`) but no methods that actually use it.
- Option A: Out of scope — fix what exists, leave handle-adapter benchmarks for later.
- Option B: In scope — add at least one `Throughput_QueueHandleAdapter` class to cover
  the reader/writer adapters.

---

## Proposed Phases (conditional on Q1=Option B, Q2=Option A, Q3=Option A)

These phases assume: move to `benchmarks/`, fix SQLite bugs, leave handle-adapter out.
Phases will be revised once open questions are answered.

### Phase 1 — Setup and file relocation
- Create `benchmarks/` directory at repo root
- Move `throughput.py` → `benchmarks/throughput.py`
- Move `throughput_results.py` → `benchmarks/throughput_results.py`
- Move `tests/tests/queuelink_throughput_test_exclude.py` → `benchmarks/throughput_test_exclude.py`
- Update `setup.cfg` to exclude `benchmarks/` from the package distribution
- Update imports in all three files to reflect new locations

### Phase 2 — Fix critical bugs in `throughput_results.py`
- Fix table creation: replace `cursor.execute('CREATE TABLE IF NOT EXISTS ?(?)', ...)`
  with direct f-string interpolation (consistent with existing `# nosec` pattern in the file)
- Fix INSERT syntax: add parentheses around `VALUES (?, ?, ?)`
- Fix `get_latest_session_id()`: `if results is not None` instead of `if len(results) > 0`
- Make DB path configurable: add a `db_path` constructor argument with a sensible default
  (e.g., `benchmarks/throughput/throughput.sqlite.db`)

### Phase 3 — Fix bugs in `throughput.py`
- Fix or remove `content_dir` / `sample_command_path` (dead code until handle-adapter
  benchmarks are added — could remove or leave with a correct path)
- Audit `queue_link.close()` coverage in `elements_per_second_queuelink`
- Fix `QUEUE_TYPE_LIST` used as a type annotation (it is a list of tuples, not a type union)

### Phase 4 — Verify and test
- Run the throughput test manually against the fixed code (outside CI, since the file
  has `_exclude` suffix)
- Ensure `tox -e pylint` and `tox -e bandit` pass with the relocated files

---

## Minimal fix alternative (if Q1=Option A)

If relocation is not in scope, the fix is smaller:

1. Fix the three SQLite bugs in `throughput_results.py` (table creation, INSERT parens,
   `len()` check)
2. Make `DB_NAME` configurable or at least absolute rather than relative
3. Fix or note the `content_dir` path issue in `throughput.py`
4. Audit `queue_link.close()` in `elements_per_second_queuelink`

Estimated: 2–3 focused changes across `throughput_results.py` and one minor fix in
`throughput.py`.
