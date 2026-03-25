# AGENTS.md

This is the canonical source of project instructions for AI coding agents.
For the rationale behind this file and the overall approach, see
[HARNESS.md](HARNESS.md).

## Build & Test

```bash
# Run tests for a single Python version
tox -e py313

# Run full matrix (all supported Python versions + lint)
tox

# Run a specific test file
tox -e py313 -- tests/tests/queuelink_test.py

# Run a specific test by keyword
tox -e py313 -- -k "test_queuelink_source_destination"

# Lint only
tox -e pylint
tox -e bandit

# Build docs locally
tox -e docs
```

Tests run in two phases per tox env (see setup.cfg):
1. Fork-context tests in parallel via pytest-xdist (`-n auto`)
2. Forkserver/spawn tests serially (xdist workers use fork, which conflicts)

## Architecture

QueueLink bridges heterogeneous queue types and file handles for concurrent Python programs.

```
src/queuelink/
├── __init__.py               # Public API surface (see "Public API" section below)
├── queuelink.py              # Core: many-to-many queue routing via publisher processes/threads
├── common.py                 # Type unions, safe_get(), is_threaded(), new_id(), constants
├── queue_handle_adapter_base.py   # Base for handle↔queue adapters
├── queue_handle_adapter_reader.py # Reads from file/pipe handles into queues
├── queue_handle_adapter_writer.py # Writes from queues to file/pipe handles
├── contentwrapper.py         # Buffers large objects to disk (pipe size limit workaround)
├── writeout.py               # UTF-8 pipe/handle writer with exception handling
├── exceptionhandler.py       # Custom exceptions: ProcessNotStarted, HandleAlreadySet, etc.
├── metrics.py                # In-process timing/counting
├── timer.py                  # High-precision timing utility
├── throughput.py             # Benchmarking: measures latency and throughput per queue/start type
├── throughput_results.py     # SQLite storage for throughput benchmark results
├── version.py                # Package version via importlib.metadata
├── link.py                   # Factory function: auto-wires source/destination pairs
└── classtemplate.py          # Logging mixin base class
```

**Key design constraint**: The library auto-detects whether queues are threading or
multiprocessing and selects Thread vs Process accordingly. Code that creates
multiprocessing primitives (Value, Lock, Event, Queue) **must** use
`multiprocessing.get_context(start_method)` — never the global `multiprocessing`
module directly — to avoid SemLock context mismatches between fork/spawn/forkserver.

## Public API

The public surface is defined in `__init__.py`. Only these names are importable
from `queuelink` directly:

- `QueueLink` — core routing class
- `DIRECTION` — enum (`FROM`/`TO`) for source/destination
- `UNION_SUPPORTED_QUEUES` — type union for all supported queue types
- `safe_get` — queue `get()` with timeout support for all queue types including SimpleQueues
- `Timer` — high-precision timing utility
- `ContentWrapper`, `WRAP_WHEN` — large-message spill-to-disk
- `QueueHandleAdapterReader` — reads from file/pipe handles into queues
- `QueueHandleAdapterWriter` — writes from queues to file/pipe handles
- `writeout` — UTF-8 pipe writer helper
- `link` — factory function: inspects source/destination types and wires the correct
  combination of `QueueLink`, `QueueHandleAdapterReader`, and/or `QueueHandleAdapterWriter`

Everything else (e.g., `common.QUEUE_TYPE_LIST`, `exceptionhandler.ProcessNotStarted`)
is internal. Import from the submodule directly if needed, but do not add to `__init__.py`
without discussion.

## Dependencies

Runtime:
- `importlib_metadata` — version detection (backport for Python 3.9)
- `kitchen` / `processrunner-kitchenpatch` — UTF-8 encoding for pipe writers (`writeout.py`)

Test:
- `parameterized` — `@parameterized_class` for cartesian test generation
- `pytest` + `pytest-cov` — test runner and coverage
- `pytest-xdist` — parallel test execution (fork-context tests only)
- `tox` — multi-environment test orchestration

Do not introduce alternative libraries for encoding or test parameterization
without checking whether the existing ones already cover the use case.

## Agent Workflow

For any non-trivial task (multiple files, multiple concerns, or more than a few
steps), agents must plan and track their work to avoid context bloat:

1. **Break the task down** into discrete, ordered steps before writing any code.
2. **Track progress in the feature directory**: for feature work, update
   `tasks/FEAT-NNN/PROGRESS.md`. For ad-hoc work outside a registered feature,
   create a `PROGRESS.md` inside a new `tasks/` subdirectory rather than in the
   repo root. Use a simple checklist format:
   ```
   # <Task Name> Progress

   - [ ] Step one
   - [x] Step two (done)
   - [ ] Step three
   ```
3. **Update the file as work proceeds** — check off completed steps and note any
   decisions or scope changes inline. This keeps the task state in a file rather
   than in the context window.
4. **Feature directories persist** until the feature is closed in `tasks/TODO.md`.
   Do not delete `tasks/FEAT-NNN/` unilaterally.

Do not rely on chat history or context memory to track multi-step progress.
The progress file is the source of truth for where the task stands.

## Task Coordination

This section applies when multiple agents work concurrently. For single-agent
work, the `*_PROGRESS.md` approach in Agent Workflow above is sufficient.

**Task board**: `tasks/TODO.md` — all work is registered here, including
features. Features appear as a single row in `tasks/TODO.md` with their detail
in `tasks/FEAT-NNN/`.

**Before starting any task**:
- Read `tasks/FEAT-NNN/PLAN.md` and `tasks/FEAT-NNN/PROGRESS.md` for the
  feature before claiming a task.
- Only claim tasks whose dependencies are all DONE.

**Claiming a task**:
- Set Status to `IN_PROGRESS` with your session ID and timestamp.
- Re-read the file immediately to verify your claim is still present — another
  agent may have claimed it in the same window. If your claim is gone, pick a
  different task. Do not skip this verification step; the re-read is the only
  guard against concurrent claims.

**While working**:
- Do not touch files listed in the `Files` field of any `IN_PROGRESS` task you
  do not own.
- Do not start Phase N+1 tasks until all Phase N tasks are DONE (phases are
  defined in the feature's `tasks/FEAT-NNN/TODO.md`).
- Record non-obvious decisions in `DECISIONS.md` (feature-scoped at
  `tasks/FEAT-NNN/DECISIONS.md`, or top-level at `tasks/DECISIONS.md`).
- Surface open questions in `PLAN.md` rather than deciding unilaterally.

**Review feedback**:
- Review documents live at `tasks/REVIEW-NNN.md` (not inside any `FEAT-NNN/`
  directory — reviews are cross-cutting).
- Each review item should include: area, severity, effort, and a brief fix
  recommendation. Group items by category (bugs, design issues, consistency,
  performance, structural).
- End every review with a Prioritization Summary table: `# | Area | Severity |
  Effort | Status`.
- Open items must be triaged into `tasks/TODO.md` (as a feature or standalone
  task) before being actioned. Do not implement review items directly without a
  corresponding task board entry.
- Mark items `✅ Resolved (FEAT-NNN)` in both the summary table and the item
  body when closed; do not delete them.

**Documentation ownership**:
- Each output file (`README.rst`, `docs/api.rst`, etc.) has one owning agent
  at a time — coordinate via the task board before editing shared doc files.
- Stub doc files with section headers during Phase 1 before implementation
  begins, so later phases have a clear target.
- Include a reconciliation task as the final phase of each feature to check
  consistency across all docs before the feature is marked complete.

## Coding Conventions

- Python 3.9+ compatibility required (no `X | Y` unions, use `Union[X, Y]`)
- Type unions for queue/lock/event types are defined in `common.py` as module-level
  constants in `UPPER_CASE_WITH_UNDERSCORES` (configured in pylint as valid type alias names)
- `@staticmethod` methods used as `Process`/`Thread` targets cannot access `self`;
  all state must be passed as arguments
- Pylint runs via tox; IDE pylint may not read `setup.cfg` `[pylint.*]` sections
- Bandit runs on `src/` only; `# nosec` comments mark intentional exceptions
  (e.g. `random.choice` for non-cryptographic IDs)
- Prefer enums over raw strings for fixed, well-known values (e.g. use
  `DIRECTION.FROM`/`DIRECTION.TO` instead of `'source'`/`'destination'`).
  String comparisons are fragile — typos produce silent failures rather than errors.
- Add a blank line after `return` (and `raise`) statements inside `if` blocks to
  visually separate independent branches. This applies within functions that contain
  multiple sequential guard clauses or classification blocks (e.g. `_is_queue()`,
  `_classify()`).
- Use `@property` only for attributes that are safe to call at any time with no
  observable side effects — i.e. pure reads of already-computed state. Do not use
  `@property` for operations that acquire locks, perform I/O, mutate state, or have
  any cost beyond a simple attribute lookup. IDEs and debuggers enumerate properties
  automatically when inspecting objects, which can trigger unintended behavior or
  mask real state. Expose such operations as explicit methods instead.
- Catch specific exception types rather than `Exception` or `BaseException`. Broad
  excepts swallow unexpected errors and make debugging harder. If a broad except is
  genuinely necessary (e.g. guarding shutdown code against unpredictable queue state),
  add an inline comment explaining why the broad catch is justified.
- Declare non-scalar variables (`list`, `dict`, `set`) before the block where they
  are first assigned, even if initially empty. This makes the expected type visible
  before the logic that populates it (e.g. `dests` in `_normalize_destination()`
  should be declared before the `if/elif/else` that assigns it). Exception: a
  comprehension that both constructs and fully populates a variable in one expression
  may be declared at use-time.

## Multiprocessing Pitfalls

These have caused real CI failures — do not repeat:

1. **Always use context-aware primitives**: `ctx = multiprocessing.get_context(start_method)`,
   then `ctx.Value()`, `ctx.Lock()`, `ctx.Event()`. Using `multiprocessing.Value()` directly
   creates primitives in the default (fork) context, causing `RuntimeError` when shared with
   spawn/forkserver processes.

2. **Never use `threading.local()` for shared counters**: Thread-local storage is per-thread.
   A value set in the main thread is invisible to worker threads. Use `ctx.Value()` even
   for thread-only mode — it works correctly across threads too.

3. **pytest-xdist + multiprocessing**: xdist workers are forked processes. Tests that
   use spawn/forkserver must run serially (without `-n auto`) to avoid SemLock conflicts.

## Test Structure

```
tests/
├── __init__.py
├── content/                        # Test fixtures and helper scripts
│   ├── line_output.py              # Generates line-based output for adapter tests
│   ├── testing_logging_config.ini  # Logging config loaded by all test setUp()
│   └── ...
├── test-output-script.py
└── tests/
    ├── __init__.py
    ├── context.py                  # Path injection: adds src/ to sys.path, loads logging config
    ├── queuelink_test.py           # Core QueueLink tests
    ├── queuelink_examples_test.py  # Tests mirroring README examples
    ├── queuelink_safe_get_test.py  # safe_get() edge cases
    ├── queuelink_handle_adapter_reader_test.py
    ├── queuelink_handle_adapter_writer_test.py
    ├── queuelink_all_adapters_test.py
    ├── contentwrapper_test.py
    ├── writeout_test.py
    ├── link_test.py                          # Tests for the link() factory function
    └── queuelink_throughput_test_exclude.py  # Benchmarks (excluded from CI)
```

### Documentation example tests

Every code example in a public-facing document (README.rst, docs/*.rst) must
have a corresponding test in `tests/tests/link_examples_test.py` (for `link()`
examples) or `tests/tests/queuelink_examples_test.py` (for direct `QueueLink`
usage). The test should mirror the example code as closely as possible and
include a docstring naming the source document and section.

When adding or changing a doc example:
1. Add or update the matching test before merging.
2. Name the test after the example (e.g., `test_quick_start_queue_to_queue`).
3. Add a docstring: `"""README: Quick start — basic queue→queue."""`

This applies to README.rst and all files under `docs/`. It does not apply to
internal comments or docstrings — only rendered public documentation.

### Test conventions

- **Two valid test styles exist**:
  1. Matrix tests for queue/start-method compatibility (primary pattern)
  2. Focused unit/example tests for isolated behavior or README-style usage
- **`context` import is required for matrix/integration-style tests** that rely on
  shared path/logging setup. Focused unit tests that import from the installed package
  path and do not require shared logging setup may omit it.
- **Parameterized matrix (for compatibility tests)**: Use `@parameterized_class` with
  the cartesian product of `QUEUE_TYPE_LIST` (9 queue types) × `PROC_START_METHODS`
  (fork, forkserver, spawn). This generates ~27 test classes per test case.
- **`queue_factory()` (for matrix queue tests)**: Provide and use `queue_factory()`
  to create queue instances from the parameterized queue type metadata. Do not create
  queue instances directly in those test methods.
- **`setUp` / `tearDown` (for start-method parameterized tests)**: Create
  `multiprocessing.get_context(self.start_method)` in `setUp`. Create a Manager only
  when the test needs manager-backed queues/proxies, and call `self.manager.shutdown()`
  in `tearDown` whenever a Manager was created.
- **Test file naming**: `*_test.py` suffix (not `test_*` prefix). Files with
  `*_test_exclude.py` suffix are intentionally excluded from collection — do not rename them.
- **Start method filtering**: Start-method-parameterized tests are split across two tox
  phases. Include `forkserver`/`spawn` in test names or parameter IDs so tox's `-k`
  filters can separate them.
- **`link()` tests use focused style (not matrix)**: `link()` abstracts queue-type and
  start-method complexity, so focused unit/example tests are preferred. The matrix is
  used only for explicit regression tests covering spawn/forkserver SemLock paths.

## Verifying Changes

After making changes, run at minimum:

```bash
# Fast check: single Python version
tox -e py313

# Lint check
tox -e pylint
tox -e bandit
```

**What to look for:**
- Tests generate many classes from the parameterized matrix. A single test failure
  often appears as multiple failures across queue types or start methods. Look for the
  common pattern — the root cause is usually in one place.
- `RuntimeError: SemLock` errors mean a multiprocessing primitive was created in the
  wrong context (see Multiprocessing Pitfalls above).
- Timeouts in CI (especially Python 3.12) can indicate a deadlock from reading a
  SimpleQueue with multiple consumers, or a missing `stop()` call on a QueueLink.
- Pylint may report issues not caught by your IDE because the tox pylint env reads
  `setup.cfg` `[pylint.*]` sections that IDEs often miss.

## CI/CD

- `.github/workflows/ci.yaml` — 25-job matrix (5 OS × 5 Python), lint, coverage
- `.github/workflows/publish.yaml` — OIDC trusted publishing to PyPI/TestPyPI
- `.github/rulesets/` — Branch and tag protection (see `rulesets/README.md`)
- Pre-commit hooks: trailing whitespace, EOF fixer, YAML/TOML checks, bandit
- Coverage uses `[coverage:paths]` to normalize cross-platform paths during combine
- Version derived from git tags via `setuptools_scm` (requires `fetch-depth: 0`)

## PR Workflow

All changes go through PRs to main (enforced by ruleset). CI must pass before merge.
Squash or rebase merges only (linear history required). Commits on main must be signed.
