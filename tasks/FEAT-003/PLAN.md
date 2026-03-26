# FEAT-003: Fix or Rebuild Throughput System — Plan

**Status**: Scoped — ready for implementation
**Decisions recorded in**: `tasks/FEAT-003/DECISIONS.md`
**Files in scope**:
- `src/queuelink/throughput.py` → relocating to `benchmarks/throughput.py`
- `src/queuelink/throughput_results.py` → relocating to `benchmarks/throughput_results.py`
- `tests/tests/queuelink_throughput_test_exclude.py` → relocating to `benchmarks/throughput_test_exclude.py`
- New: `benchmarks/content/line_output.py` (copy of `tests/content/line_output.py`)
- New: `benchmarks/context.py` (path bootstrap for benchmark scripts)

---

## Decisions

| Q | Question | Answer |
|---|---|---|
| Q1 | Relocate or fix in place? | **B — move to `benchmarks/`** |
| Q2 | Keep SQLite or simplify storage? | **A — fix SQLite, keep it** |
| Q3 | Include handle-adapter benchmarks? | **B — yes, add them** |

Rationale recorded in `DECISIONS.md`.

---

## Known Bugs to Fix

### `throughput_results.py` (all critical — system does not run today)

1. **Table creation uses `?` placeholder for table name** (`__init__`, line 45)
   SQLite3 does not support parameterized identifiers. Current code raises
   `sqlite3.OperationalError` unconditionally at construction time.
   Fix: f-string interpolation with `# nosec`, consistent with existing pattern
   in the file (`update_session_id`, `start_session`, `put`).

2. **INSERT missing parentheses** (`update_session_id`, line 69–70)
   `VALUES ?, ?, ?` → must be `VALUES (?, ?, ?)`. Raises `sqlite3.OperationalError`
   on every session write.

3. **`get_latest_session_id()` calls `len()` on a `sqlite3.Row`** (line 118)
   `fetchone()` returns a `Row` or `None`, not a list. `len(row)` returns column
   count (not row count), so the guard `if len(results) > 0` is always truthy when
   a row exists. Fix: `if results is not None`.

4. **DB path is hardcoded and relative** (`DB_NAME = 'throughput/throughput.sqlite.db'`)
   This resolves relative to the current working directory at runtime — unpredictable.
   Fix: make `db_path` a constructor argument with a default that resolves to
   `benchmarks/throughput/throughput.sqlite.db` relative to the file's location.

### `throughput.py`

5. **`content_dir` path is wrong** (`Throughput.__init__`, line 97–98)
   Currently resolves to `src/content/`, which does not exist. The fixture is at
   `tests/content/line_output.py`. After relocation to `benchmarks/`, the correct
   relative path is `../tests/content/`.
   Fix during relocation: resolve to `os.path.join(os.path.dirname(__file__), '..', 'tests', 'content')`.
   Note: this creates a benchmarks → tests dependency, which is acceptable for
   developer-only tooling.

6. **`queue_link.close()` not called on all exit paths** (`elements_per_second_queuelink`)
   The QueueLink created for the actual measurement is closed after the loop, but if
   `elements_per_seconds_increase` raises `ValueError` early (element count too high),
   the link leaks. Fix: wrap in try/finally.

7. **`QUEUE_TYPE_LIST` used as a type annotation** (function signatures in `throughput.py`)
   `QUEUE_TYPE_LIST` is a `List[Tuple]`, not a type union. Type annotations that
   accept queue instances should use `UNION_SUPPORTED_QUEUES`. Fix during relocation.

---

## Phased Implementation

### Phase 1 — Relocation

**Goal**: Move files out of `src/queuelink/` into `benchmarks/`. No logic changes yet.

Tasks:
1. Create `benchmarks/` directory with `__init__.py` stub
2. Copy `tests/content/line_output.py` → `benchmarks/content/line_output.py`
   (gives benchmarks self-contained fixture; avoids benchmarks → tests dependency)
3. Create `benchmarks/context.py`: adds `benchmarks/` to `sys.path` so intra-benchmark
   imports resolve correctly when run as scripts
4. Move `src/queuelink/throughput_results.py` → `benchmarks/throughput_results.py`
   - No import changes needed (only uses stdlib: `os`, `sqlite3`, `sys`, `datetime`)
5. Move `src/queuelink/throughput.py` → `benchmarks/throughput.py`
   - Change `from queuelink.throughput_results import ThroughputResults` →
     `from throughput_results import ThroughputResults` (resolved via `context.py`)
   - Change `from queuelink.common import ...` → remains the same (installed package)
6. Move `tests/tests/queuelink_throughput_test_exclude.py` →
   `benchmarks/throughput_test_exclude.py`
   - Remove `from tests.tests import context`; replace with `import context` (local)
   - Update `from queuelink.throughput import ...` → `from throughput import ...`
7. Delete the original files from `src/queuelink/` and `tests/tests/`
8. Verify `tox -e pylint` and `tox -e bandit` still pass (both target `src/` only;
   removing files should not introduce new failures)

No `setup.cfg` changes required — `[options.packages.find] include=queuelink` already
excludes everything outside `src/queuelink/`.

---

### Phase 2 — Fix `throughput_results.py` bugs

**Goal**: Make `ThroughputResults` and `ThroughputResultsOutput` actually work.

Tasks:
1. Fix table creation: replace `cursor.execute('CREATE TABLE IF NOT EXISTS ?(?)', (tbl, schema))`
   with f-string interpolation. Table names and schema strings are defined as module-level
   constants — not user input — so f-string SQL is acceptable here (consistent with
   existing `# nosec` usage in the file).
2. Fix INSERT parentheses: `VALUES ?, ?, ?` → `VALUES (?, ?, ?)`
3. Fix `get_latest_session_id()`: replace `if len(results) > 0` with `if results is not None`
4. Make DB path configurable: add `db_path: str = None` to `ThroughputResults.__init__`
   and `ThroughputResultsOutput.__init__`. When `None`, default to
   `os.path.join(os.path.dirname(__file__), 'throughput', 'throughput.sqlite.db')`.
   Create the parent directory automatically if it does not exist (`os.makedirs`).
5. Propagate `db_path` from `Throughput_QueueLink` constructor through to `ThroughputResults`.

---

### Phase 3 — Fix `throughput.py` bugs

**Goal**: Fix remaining bugs in the existing `Throughput_QueueLink` implementation.

Tasks:
1. Fix `content_dir` path: update to resolve correctly from `benchmarks/` location.
   Since `line_output.py` is now in `benchmarks/content/`, use:
   `os.path.join(os.path.dirname(__file__), 'content')`
2. Fix `queue_link.close()` coverage in `elements_per_second_queuelink`: wrap the
   QueueLink creation and usage in a try/finally block.
3. Fix type annotations: replace `QUEUE_TYPE_LIST` used as a type hint with
   `UNION_SUPPORTED_QUEUES` (imported from `queuelink.common`).

---

### Phase 4 — Add handle-adapter benchmarks

**Goal**: Add `Throughput_QueueHandleAdapterReader` and `Throughput_QueueHandleAdapterWriter`
classes to cover `QueueHandleAdapterReader` and `QueueHandleAdapterWriter` throughput.

#### `Throughput_QueueHandleAdapterReader`

Measures: time to first line, lines per second.

Design:
- Subprocess runs `benchmarks/content/line_output.py -l <N>`, writing N lines to stdout
- Subprocess stdout pipe connected to a `QueueHandleAdapterReader` → queue
- Benchmark consumes queue output and measures timing

Methods:
- `time_to_first_line(queue_type)`: spawn subprocess (1 line), start adapter, time until
  first item arrives in queue
- `lines_per_second(queue_type, line_count)`: send N lines via subprocess, measure
  total elapsed time and compute rate

#### `Throughput_QueueHandleAdapterWriter`

Measures: lines per second writing from queue to a file handle.

Design:
- Pre-fill a source queue with N text lines
- Attach a `QueueHandleAdapterWriter` writing to a `tempfile.NamedTemporaryFile`
- Measure time until all lines are written (detected by file size or line count)

Methods:
- `lines_per_second(queue_type, line_count)`: pre-fill queue, start writer, measure rate

#### Test additions (`benchmarks/throughput_test_exclude.py`)

- `QueueHandleAdapterReaderThroughputTestCase`: parameterized over `QUEUE_TYPE_LIST`
  and `PROC_START_METHODS`, tests `time_to_first_line` and `lines_per_second`
- `QueueHandleAdapterWriterThroughputTestCase`: same parameterization, tests
  `lines_per_second`

Both classes store results via `ThroughputResults` so they appear in the same SQLite
session alongside `QueueLink` results.

---

### Phase 5 — Verify

Tasks:
1. Run `tox -e pylint` — confirm no regressions from the `src/` removal
2. Run `tox -e bandit` — confirm clean (neither tool touches `benchmarks/`)
3. Manual smoke test: run `python benchmarks/throughput_test_exclude.py` from repo root
   for a single queue type / start method combination and confirm results are written
   to the DB without error
4. Run `python -m benchmarks.throughput_results` (or the `__main__` block) and confirm
   results are printed correctly

---

## Notes

- `benchmarks/` is intentionally not a tox target. These are manual developer tools,
  not CI artefacts.
- The `_test_exclude.py` suffix is already established convention for keeping throughput
  tests out of pytest collection.
- `context.py` in `benchmarks/` follows the same pattern as `tests/tests/context.py` —
  it is imported for its side effect of setting up `sys.path`.
