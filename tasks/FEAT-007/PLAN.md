# FEAT-007: Publisher Restart on New Destination — Plan

**Status**: NOT_STARTED — high effort; needs human scoping before any work begins
**Source**: REVIEW-001 item 3
**Files in scope**: `src/queuelink/queuelink.py`

---

## Problem

When a new destination queue is registered via `register_queue()`, all active
publishers are stopped and restarted with the updated destination dict. For $n$ source
queues, one new destination causes $n$ publisher restarts — each of which may involve
process creation overhead (especially for spawn/forkserver start methods).

The root cause: publishers receive the destination dict at start time rather than
holding a shared reference to a live, mutable dict.

---

## Options

**Option A — Document and accept**: For the typical use case (few sources, destinations
configured at startup), the restart cost is negligible. Add an explicit O(n) restart
note to the `register_queue()` docstring and to AGENTS.md.

**Option B — Shared proxy dict**: Pass a `Manager().dict()` as the destination
container so publishers see updates without restart.
- Trade-off: Adds a Manager dependency and proxy overhead on every `put()`.
- Complexity: Medium. Requires careful handling of Manager lifecycle.

**Option C — Reload signal**: Send a sentinel into the source queue that tells the
publisher to re-read destinations from a shared structure.
- Trade-off: Introduces coupling between the sentinel protocol and message content.
- Complexity: Medium-High. Must ensure sentinels are not forwarded to consumers.

---

## Recommendation

Start with Option A (document) unless profiling shows restart cost is a real bottleneck
in practice. Options B and C are meaningful refactors that should only be pursued with
evidence that the current behavior is causing problems.

---

## Open Questions (resolve with human before starting)

- Q1: Has publisher restart latency been observed as a real issue? If so, in what context?
- Q2: If a code fix is desired, prefer Option B or C?
- Q3: Is there an acceptable upper bound on destinations-per-link that keeps Option A viable?
