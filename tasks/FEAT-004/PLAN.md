# FEAT-004: API and Exception Handler Polish — Plan

**Status**: NOT_STARTED — needs scoping before implementation
**Source**: REVIEW-001 items 5, 6
**Files in scope**: `src/queuelink/exceptionhandler.py`, `src/queuelink/queuelink.py`

---

## Items to Address

### Item 5 — `ExceptionHandler` naming confusion (REVIEW-001)

`ExceptionHandler` inherits from `Exception` but is never raised. It is a logging
utility called for its side effects. This is confusing — it looks like a base class
for custom exceptions.

**Options**:
- (a) Make it a plain function `log_exception(error, message)` — no `Exception` inheritance
- (b) Add a clear docstring stating it is a logging utility, not an exception type

Preferred: (a) — removes the misleading inheritance. Requires updating all call sites.

### Item 6 — `QueueLink.is_alive()` raises `ProcessNotStarted` (REVIEW-001)

Before any queues are registered, `is_alive()` raises `ProcessNotStarted` rather than
returning `False`. Normal Python convention for `is_alive()` checks is to return a bool.

**Fix**: Return `False` when `started` is not set, consistent with
`threading.Thread.is_alive()` and `multiprocessing.Process.is_alive()`.

---

## Open Questions

- Q1: For item 5, refactor to plain function or just add a docstring?
  **Finding (2026-03-27)**: `ExceptionHandler` IS raised in `writeout.py` (2 places):
  `raise ExceptionHandler(exc, 'Crazy pipe writer stuff: ...')` and
  `raise ExceptionHandler(exc, 'writeout caught odd error: ...')`.
  The PLAN description that it is "never raised" is incorrect.
  - Option (a) still viable: change writeout.py to log then re-raise the original exception
    (e.g., `log_exception(exc, msg); raise exc`). Cleaner exception semantics.
  - Option (b) simpler: add a docstring clarifying that ExceptionHandler is both a logging
    utility AND wraps the original exception for callers that catch it.
  No tests catch ExceptionHandler — confirmed by grep over tests/ directory.
  **Please confirm which option before implementing.**
  **Decision (2026-04-05)**: Implementing Option (a) per user instruction to complete all features up to FEAT-008.

- Q2: Are there call sites for `ExceptionHandler` outside `src/queuelink/`?
  **Finding (2026-03-27)**: Only `writeout.py` calls it. No test files reference it.
  Safe to refactor without test changes.
