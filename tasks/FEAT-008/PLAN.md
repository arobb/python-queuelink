# FEAT-008: Windows Support — Plan

**Status**: NOT_STARTED — needs investigation pass before implementation
**Files in scope**: `src/queuelink/common.py`, `setup.cfg`, `.github/workflows/ci.yaml`,
and potentially `src/queuelink/writeout.py`, `src/queuelink/contentwrapper.py`

---

## Background

The library currently targets Linux and macOS only. Evidence:

- `setup.cfg` `[testenv]` has `platform = linux|darwin` — tox explicitly skips the test
  environment on Windows without error
- No Windows runners in `.github/workflows/ci.yaml`
- `PROC_START_METHODS = ['fork', 'forkserver', 'spawn']` in `common.py` — Windows only
  supports `spawn`; `fork` and `forkserver` are Unix-only
- The two-phase tox test split (Run 1: fork-based; Run 2: forkserver/spawn) assumes
  `fork` is available as the baseline start method
- CI coverage rename step uses `if [ -f ... ]; then mv ...; fi` (bash) — does not
  work in PowerShell on Windows runners

---

## Known Blockers

### 1. Start method availability

| Start method | Linux | macOS | Windows |
|---|---|---|---|
| `fork` | ✅ | ✅ | ✗ |
| `forkserver` | ✅ | ✅ | ✗ |
| `spawn` | ✅ | ✅ | ✅ |

`PROC_START_METHODS` is used as a test parameterization list and in `ConcurrentContext`.
On Windows, `multiprocessing.get_context('fork')` raises `ValueError`. Any test or
benchmark parameterized over all three start methods will fail on Windows unless
`fork` and `forkserver` are filtered out.

### 2. Two-phase tox test split

The tox `[testenv]` runs two pytest commands:
- Run 1: `-k "not forkserver and not spawn"` (i.e., fork-only tests)
- Run 2: `-k "forkserver or spawn"` (i.e., forkserver + spawn tests)

On Windows, Run 1 would select all tests that include `fork` (which would fail) and
Run 2 would select spawn-only tests. The split needs a Windows-aware alternative:
- Windows: single run with `-k "spawn"` (no fork, no forkserver)
- Linux/macOS: current two-phase split preserved

### 3. `kitchen` / `kitchenpatch` dependency

`writeout.py` and `contentwrapper.py` use `kitchen` / `processrunner-kitchenpatch` for
UTF-8 encoding. Windows compatibility of these packages is unknown and must be verified
before committing to this approach. If they do not work on Windows, a fallback path or
replacement is needed (see also FEAT-006, which already proposes encoding unification).

### 4. CI coverage rename step

```yaml
- name: Suffix coverage data file for artifact merge
  run: |
    if [ -f coverage/coverage ]; then
      mv coverage/coverage \
         "coverage/coverage.${{ matrix.os }}.${{ matrix.python-version }}"
    fi
```

This is a bash `if` statement. Windows runners use PowerShell by default. Needs to be
replaced with a cross-platform approach (e.g., a Python one-liner or a `shell: bash`
annotation using Git Bash, which is available on GitHub-hosted Windows runners).

### 5. `platform = linux|darwin` in `setup.cfg`

The tox platform constraint silently skips the test env on Windows. This must be
removed or replaced with a Windows-aware tox configuration.

---

## Open Questions (resolve before implementation)

**Q1 — `kitchen`/`kitchenpatch` Windows compatibility?**
Install `kitchen` and `processrunner-kitchenpatch` in a Windows environment and verify
`writeout.py` and `contentwrapper.py` work. If not, Windows support depends on FEAT-006
(encoding unification) landing first, or a conditional import fallback.

**Q2 — Tox configuration strategy: one env or two?**
- Option A: Extend the existing `[testenv]` with a Windows-aware command block using
  `{env:OS:}` or a `platform`-conditional tox factor
- Option B: Add a separate `[testenv:windows]` that only runs spawn tests
- Option C: Use a `conftest.py` pytest fixture to skip `fork`/`forkserver` tests when
  the platform does not support them, and keep a single tox env

Option C (conftest skip) is the cleanest: the test suite self-adapts rather than
requiring platform-specific tox configuration.

**Q3 — Which Windows runner version(s) to target?**
GitHub-hosted options: `windows-2022`, `windows-2025` (= `windows-latest`).
Recommend starting with `windows-latest` (one runner) and expanding if needed.

**Q4 — Is `fork` behavior on WSL2 in scope?**
WSL2 (Windows Subsystem for Linux) supports `fork`. This is out of scope — the target
is native Windows Python, not WSL2.

---

## Proposed Phases

### Phase 1 — Compatibility audit

1. Verify `kitchen` / `kitchenpatch` install and run on Windows (Python 3.9–3.13)
2. Run a minimal smoke test of `QueueLink` with `spawn` on Windows
3. Identify any other Unix-only calls in `src/queuelink/` (e.g., `signal`, `fcntl`,
   platform-specific `multiprocessing.connection` behavior)
4. Document findings; determine if FEAT-006 must land before FEAT-008

### Phase 2 — Platform-aware start method list

1. Make `PROC_START_METHODS` platform-aware in `common.py`:
   ```python
   import sys
   PROC_START_METHODS = ['fork', 'forkserver', 'spawn'] \
       if sys.platform != 'win32' else ['spawn']
   ```
   This automatically propagates to all parameterized tests and benchmarks.

2. Verify `ConcurrentContext` (in `throughput.py`) handles `spawn`-only gracefully.

### Phase 3 — Test suite adaptation

1. Add a `conftest.py` (or extend the existing one) to skip tests that require
   `fork`/`forkserver` when `sys.platform == 'win32'`. Alternative: the
   `PROC_START_METHODS` change in Phase 2 may be sufficient if parameterization
   is purely driven by that list.

2. Fix the two-phase tox test split for Windows. The cleanest approach (Option C from
   open questions) is to keep a single pytest invocation on Windows by adding:
   - A tox factor or platform condition that selects the correct `-k` expression
   - Or: restructure so that Run 1 uses `-k "not spawn and not forkserver"` (already
     correct for Linux/macOS) and Run 2 uses `-k "spawn"` on Windows (omitting
     `forkserver`).

3. Remove `platform = linux|darwin` from `setup.cfg` `[testenv]`. Replace with any
   necessary Windows-conditional command logic.

### Phase 4 — CI changes

1. Add Windows runner to `ci.yaml` matrix:
   ```yaml
   - windows-latest  # Windows Server 2025
   ```
   Start with a single Windows version. Expand later if needed.

2. Fix coverage rename step — use `shell: bash` (Git Bash is available on Windows
   GitHub-hosted runners) or replace with a Python one-liner:
   ```yaml
   - name: Suffix coverage data file for artifact merge
     shell: bash
     run: |
       if [ -f coverage/coverage ]; then
         mv coverage/coverage \
            "coverage/coverage.${{ matrix.os }}.${{ matrix.python-version }}"
       fi
   ```
   Adding `shell: bash` is the minimal change; it relies on Git Bash being present,
   which it is on all GitHub-hosted Windows runners.

3. Update `[coverage:paths]` in `setup.cfg` to include Windows path patterns if needed
   for coverage combine across OS families.

### Phase 5 — Verify

1. CI passes on `windows-latest` for all supported Python versions (spawn-only tests)
2. `tox -e py313` runs locally on Windows without skipping or erroring
3. Fork/forkserver tests are clearly skipped (not failed) on Windows
4. Coverage combine includes Windows data files correctly

---

## Dependencies

- Phase 1 (audit) determines whether FEAT-006 (encoding) must land first
- FEAT-003 Phase 1 (benchmarks relocation) should complete before FEAT-008 touches
  `setup.cfg` to avoid conflicts

---

## Notes

- Python's `multiprocessing` default start method on Windows has always been `spawn`.
  The library's context-aware primitive usage (`ctx.Value()`, `ctx.Lock()` etc.) is
  already correct for spawn — this was enforced to fix earlier CI failures on Linux.
  The multiprocessing mechanics should work on Windows without changes.
- Windows path separators (`\`) are not expected to cause issues since the library
  does not construct paths from string literals, but this should be confirmed during
  Phase 1.
- The 25-job CI matrix would grow to 30 jobs (5 Python versions × 6 OS variants) with
  one Windows runner added.
