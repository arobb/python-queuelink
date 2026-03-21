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
├── link.py                   # Stub — factory function (not yet implemented)
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

## Coding Conventions

- Python 3.9+ compatibility required (no `X | Y` unions, use `Union[X, Y]`)
- Type unions for queue/lock/event types are defined in `common.py` as module-level
  constants in `UPPER_CASE_WITH_UNDERSCORES` (configured in pylint as valid type alias names)
- `@staticmethod` methods used as `Process`/`Thread` targets cannot access `self`;
  all state must be passed as arguments
- Pylint runs via tox; IDE pylint may not read `setup.cfg` `[pylint.*]` sections
- Bandit runs on `src/` only; `# nosec` comments mark intentional exceptions
  (e.g. `random.choice` for non-cryptographic IDs)

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
    └── queuelink_throughput_test_exclude.py  # Benchmarks (excluded from CI)
```

### Test conventions

- **Every test file** must `from tests.tests import context` to configure `sys.path` and logging.
- **Parameterized matrix**: Tests use `@parameterized_class` with the cartesian product
  of `QUEUE_TYPE_LIST` (9 queue types) × `PROC_START_METHODS` (fork, forkserver, spawn).
  This generates ~27 test classes per test case. New tests should follow this pattern.
- **`queue_factory()`**: Each test class provides a `queue_factory()` method that creates
  the correct queue type based on `self.module` and `self.class_name`. Use it — do not
  create queues directly in test methods.
- **`setUp` / `tearDown`**: Always create a `multiprocessing.get_context(self.start_method)`
  context and a Manager in `setUp`, and call `self.manager.shutdown()` in `tearDown`.
- **Test file naming**: `*_test.py` suffix (not `test_*` prefix). Files with
  `*_test_exclude.py` suffix are intentionally excluded from collection — do not rename them.
- **Start method filtering**: Tests parameterized by start method are automatically
  split across the two tox phases. Use `forkserver` or `spawn` in the test name/parameter
  so tox's `-k` filter can separate them.

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
