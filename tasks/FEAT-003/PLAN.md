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

### Phase 2 — Fix `throughput_results.py` bugs + add host context

**Goal**: Make `ThroughputResults` and `ThroughputResultsOutput` actually work, and
capture enough host context alongside results that they are interpretable across machines.

#### Bug fixes

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

#### Host context — schema addition

Without knowing the machine the benchmarks ran on, results are hard to interpret.
A result of "500 elements/second" is meaningless without knowing whether it came from
a laptop under load or a dedicated server. The session table should capture enough
host information to make results comparable.

Add a `host_info` table (one row per session):

```
session_id, hostname, cpu_model, cpu_count, python_version, os_platform
```

All fields populated using stdlib only (`platform`, `os`, `sys`) — no new runtime
dependencies:

| Field | Source |
|---|---|
| `hostname` | `platform.node()` |
| `cpu_model` | `platform.processor()` (may be empty on some platforms; acceptable) |
| `cpu_count` | `os.cpu_count()` |
| `python_version` | `sys.version` |
| `os_platform` | `platform.platform()` |

This row is written once per session in `ThroughputResults.__init__` alongside the
existing `sessions` table entry.

**What this gives users**: When comparing results across machines or Python versions,
the `host_info` join tells them exactly what hardware and OS produced the numbers.
The `python_version` column is redundant with the per-result column that already exists
but is worth having at session scope for quick filtering.

**What it does not give**: real-time load or memory pressure at run time. Those require
`psutil` (not a current dependency) and add noise to results rather than explaining them.
Document this limitation in `benchmarks/README.md` (Phase 6) with a note about
running benchmarks on an otherwise-idle machine for most reproducible results.

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
3. Manual smoke test: run a single queue type / start method combination end-to-end
   and confirm results (including `host_info` row) are written to the DB without error
4. Run `python benchmarks/throughput_results.py` (the `__main__` block) and confirm
   results are printed correctly with host context visible

---

### Phase 6 — Runner documentation (`benchmarks/README.md`)

**Goal**: Make it clear when to run the benchmarks, how to interpret results, and how
host context affects the numbers.

#### When to run

Throughput benchmarks are **not** CI artefacts. They are developer tools for:

1. **Pre-release baseline capture**: Run before tagging a release to establish a
   performance baseline for that version. Store the DB output alongside the tag.
2. **Change validation**: Run before and after a change suspected to affect throughput
   (e.g., changes to `queuelink.py` publisher loop, `safe_get()`, adapter I/O path).
   Compare the two sessions in the DB.
3. **Environment profiling**: Run on a new machine or Python version to establish what
   to expect for that environment.

They should **not** run in standard CI because:
- CI runners vary in available CPU, load, and OS configuration — results are not comparable
- The full matrix (9 queue types × 3 start methods × 5 rounds × 3 test functions) is slow
- Timing-sensitive tests produce flaky results in shared environments

**If a consistent reference baseline is desired**, consider a manually-triggered
GitHub Actions `workflow_dispatch` job pinned to a self-hosted or large runner, with
results committed to a `benchmarks/results/` directory in the repo.

#### How to interpret results

The benchmark captures three metrics per (queue_type, start_method) combination:

| Metric | What it measures | What affects it most |
|---|---|---|
| `time_to_first_element` | Startup latency (process/thread creation + first message) | start_method (spawn > forkserver > fork); queue type |
| `avg_time_per_element` | Steady-state per-message latency after warmup | Queue type; OS scheduling |
| `elements_per_second` | Sustained throughput; reported as actual vs baseline ratio | CPU speed; queue contention; start_method |

**Key interpretation rule**: The `elements_per_second_queuelink_baseline` measures direct
queue put/get speed on the same machine. The `_actual` result adds the QueueLink publisher
in the middle. The ratio `actual / baseline` is the most comparable number across machines
— it normalises out raw CPU speed and measures the overhead introduced by QueueLink itself.

A ratio close to 1.0 means QueueLink adds negligible overhead. A ratio significantly below
1.0 indicates the publisher loop or queue type is a bottleneck.

#### How host context is recorded

Each benchmark session writes a `host_info` row to the SQLite DB:

```sql
SELECT h.hostname, h.cpu_model, h.cpu_count, h.os_platform,
       r.test_name, r.start_method, r.source, r.destination,
       AVG(CAST(r.result AS REAL)) as avg_result, r.result_unit
FROM results r
JOIN host_info h ON r.session_id = h.session_id
WHERE r.session_id = '<session_id>'
GROUP BY r.test_name, r.start_method, r.source, r.destination, r.result_unit
ORDER BY r.test_name, r.start_method;
```

This lets you join results to the machine that produced them when comparing across
environments.

#### Best practices for reproducible results

- Run on an otherwise-idle machine (no concurrent browser, compilation jobs, etc.)
- Use a consistent Python version (results vary across CPython releases)
- Run the full 5-round parameterisation (default) and use the averaged result
- Note: `spawn` and `forkserver` start methods are always slower than `fork` on first
  element — this is expected (process startup cost), not a bug

#### Tasks

1. Create `benchmarks/README.md` with the above content
2. Add a one-line note to the top-level `README.rst` pointing to `benchmarks/README.md`
   for users interested in performance numbers

---

## Notes

- `benchmarks/` is intentionally not a tox target. These are manual developer tools,
  not CI artefacts.
- The `_test_exclude.py` suffix is already established convention for keeping throughput
  tests out of pytest collection.
- `context.py` in `benchmarks/` follows the same pattern as `tests/tests/context.py` —
  it is imported for its side effect of setting up `sys.path`.
