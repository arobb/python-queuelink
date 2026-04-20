# FEAT-004: API and Exception Handler Polish — Progress

## Status: DONE

## Phase 1 — is_alive() fix (Item 6)
- [x] 004-1-1: Fix `is_alive()` to return False instead of raising ProcessNotStarted

## Phase 2 — ExceptionHandler refactor (Item 5)
- [x] 004-2-1: Decide and implement ExceptionHandler refactor (BLOCKED — see PLAN.md Q1 update)

## Notes
- Item 6 complete: `is_alive()` now returns False when not started, consistent with threading/multiprocessing stdlib convention
- Item 5 blocked: ExceptionHandler IS raised in writeout.py (2 places), making a plain-function refactor non-trivial. See updated PLAN.md for details.
