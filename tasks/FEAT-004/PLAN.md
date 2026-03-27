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

## Open Questions (resolve before starting)

- Q1: For item 5, refactor to plain function or just add a docstring?
- Q2: Are there call sites for `ExceptionHandler` outside `src/queuelink/`?
  (Check tests and any downstream usage before renaming.)
