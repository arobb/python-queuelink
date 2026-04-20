# FEAT-007: Publisher Restart on New Destination — Progress

## Status: DONE

## Phase 1 — Document O(n) restart behavior (Option A)
- [x] 007-1-1: Add O(n) restart note to `register_queue()` docstring in queuelink.py
- [x] 007-1-2: Feature closed with Option A — documentation-only fix per PLAN.md recommendation.
  Q1/Q2/Q3 remain open if a code fix is desired in the future; closing as DONE
  because Option A is complete and sufficient per the plan.

## Notes
- Option A (document) implemented per PLAN.md recommendation
- Code-fix options (B/C) deferred; no evidence of real-world restart latency issues
