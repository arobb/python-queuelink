# FEAT-010: Core Correctness Fixes Progress

## Status: DONE (2026-09-29) — all phases complete, including the Q5 fix (010-2-8) and REVIEW-002 reconciliation, independently re-verified by L0

## Checklist

- [x] Resolve open questions Q1–Q4 in PLAN.md (see DECISIONS.md)
- [x] Phase 1 — small fixes (fsync, int IDs, Event truthiness, EOFError, direction)
- [x] Phase 2 — put-side bounded wait, partial fan-out semantics, `link_timeout` default, `safe_get` docstring
      (010-2-5 `connection.wait` DEFERRED per DECISIONS.md Q4)
- [x] Phase 2 — baseline and post-change benchmark numbers recorded below
- [x] Phase 2 — 010-2-8 Q5 fix (unread unbounded `multiprocessing.Queue`/`JoinableQueue`
      destination no longer hangs a process publisher's exit), with regression tests
- [x] Phase 3 — regression tests for Phase 1 bugs (010-3-2..010-3-5)
- [x] Phase 3 — 010-3-1 (full-destination hang; thread + process queues × all
      start methods, incl. `register_queue(TO)`) and 010-3-6 (`queue.SimpleQueue`
      takes the native `get(timeout=)` path)
- [x] Phase 4 — README "Tuning link_timeout", `docs/link_guide.rst` `link_timeout`
      entry, CHANGELOG `Changed` (default) + `Fixed` (full-destination hang)
- [x] Phase 4 — REVIEW-002 reconciliation (010-4-3, done by L0)

## Benchmarks

| Metric | Before | After |
|--------|--------|-------|
| Idle CPU per publisher — thread (`queue.Queue`) | 2.78% (rerun 2.62%) | 0.29% (rerun 0.30%) |
| Idle CPU per publisher — process (`multiprocessing.Queue`, fork) | 2.60% (rerun 2.80%) | 0.40% (rerun 0.40%) |
| `stop()` latency (idle) — thread | 5.07 ms median, 11.4 ms max | 60.6 ms median, 99.3 ms max |
| `stop()` latency (idle) — process (fork) | 11.6 ms median, 14.9 ms max | 59.1 ms median, 104.2 ms max |
| Throughput (elements/s, `queue.Queue`→`queue.Queue`, fork, 5 rounds) | 2111 avg (1796–2355) | 2053 avg (1978–2164) |

Before = `link_timeout=0.01`, after = `link_timeout=0.1`. Python 3.11.2, 2-vCPU Linux
sandbox VM (shared, so noisy).

Methodology:

- **Idle CPU**: an ad hoc script, run manually and not committed. It starts one
  `QueueLink` with nothing flowing, lets it settle, then samples CPU over a 5 s
  wall-clock window, 3 rounds, median reported.
  - Thread publisher: `time.process_time()` delta minus the same window with no
    link running.
  - Process publisher: the child's `utime+stime` from `/proc/<pid>/stat`.
- **`stop()` latency**: wall-clock time of `ql.stop()` with nothing in flight,
  40 rounds. The delay before each `stop()` is randomized (0.3–0.6 s).
  - The first "before" run used a fixed 0.3 s delay. That delay phase-locks with
    the `get(timeout=)` cycle and hid the wakeup latency: it reported 1.8 ms for
    the new default. Those numbers were discarded.
  - Both columns of the table come from the randomized rerun, on the same code
    with `link_timeout` passed explicitly. The idle path does not touch the
    put-side change, so this is equivalent to the pre-change code.
  - The idle-CPU "before" figure is from the original pre-change run. The rerun
    value is in parentheses.
- **Throughput**: the existing suite's `elements_per_second_queuelink` for
  `queue.Queue`→`queue.Queue`, fork, 5 rounds (`QueueLinkThroughputTestCase_750..754_fork`),
  run against the working tree with `PYTHONPATH=src`.
  - `benchmarks/README.md`'s quick `-k "queue_Queue_and_fork_and_index_1"` filter no
    longer matches anything: parameterized class names are now `..._<N>_fork`.
  - The raw-queue baseline in the same sessions moved from 4949 to 4556 el/s (−8%).
    The QueueLink figure moved −2.7%, well inside its per-round spread. So throughput
    is unchanged within noise.

Conclusion: idle CPU per publisher dropped about 9×. Worst-case idle `stop()`
latency rose from about `link_timeout` = 10 ms to about 100 ms, which matches
Q3's expectation. Throughput did not change. This supports the README claim
that the timeout adds no message latency: `get(timeout=)` returns when an item
arrives.

## Notes

- 010-2-1: `put(timeout=)` support is detected once per destination from its
  signature, not by catching `TypeError` from `put()`. See DECISIONS.md.
- 010-2-2: a stopping publisher still makes one bounded put attempt to each remaining
  destination. It abandons only destinations that stay full. `task_done()` is called
  once that decision has been made for every destination, then the publisher logs a
  warning and exits.
- 010-3-1: all 11 thread/fork tests fail against the old unbounded put. This was
  checked by monkeypatching `_put_until_stopped` back to a plain `put()` in a throwaway
  pytest plugin; spawn/forkserver cannot be patched that way. They all pass with the fix.
- Found while probing: an *unbounded*, unread `multiprocessing.Queue` destination
  still hangs a process publisher's exit, because the feeder thread flushes at exit.
  This existed before this change. Raised as PLAN.md Q5 for L0. Fixed in 010-2-8,
  below.
- 010-2-8 (Q5): the module-level `_release_destinations()` helper runs at all four
  `_publisher` return points. It differs from a bare `cancel_join_thread()` in two ways:
  - **It flushes before it cancels.** A bare `cancel_join_thread()` at exit loses
    items on the happy path. It drops whatever is still in the publisher's
    feeder-thread buffer, including items the publisher already took from the source
    for a destination that *is* being read. A manual probe put 3000 × 4 KiB items
    through a process publisher with a live consumer, then called `stop()` once the
    source was drained. With the bare cancel, 2/10 runs lost items (2968 and 2463
    received), plus another run of 2144 in an earlier probe. With the pre-fix code
    and with the final fix, 3000/3000 in every run.
    So the helper now calls `close()` and runs `join_thread()` in a daemon thread
    for every such destination. All destinations share one `timeout` (`link_timeout`)
    deadline, the same bound Q2 gives a stopping publisher's last `put()`. Only
    destinations still unflushed at the deadline get `cancel_join_thread()`, plus a
    warning naming them. It uses only public API.
  - **Process publishers only.** The helper returns immediately unless it is running
    on the main thread, and a thread publisher never is. A thread publisher's
    destinations are the caller's own queue objects. Closing them breaks the caller's
    later `put()`s (verified: `ValueError: Queue ... is closed`). Cancelling their
    join makes the *caller's* process drop its own buffered puts at exit.
  - The hang reproduced under fork, spawn and forkserver before the fix
    (`stop()` never returned). After the fix `stop()` returns in about 0.13–0.15 s.
  - Tests: `QueueLinkUnreadDestinationStopProcessTest` (mp `Queue`/`JoinableQueue` ×
    3 start methods: all 6 fail before, pass after).
    `QueueLinkStopFlushesDestinationTest` fails in about half of runs against the bare
    cancel, and passed 5/5 targeted runs with the fix.
    `QueueLinkThreadPublisherLeavesDestinationOpenTest` fails if the main-thread
    guard is removed.
  - The multiprocessing.SimpleQueue case is still a known limitation, per
    DECISIONS.md Q5.
- `_publisher` now carries `# pylint: disable=too-many-locals,too-many-statements`.
  `too-many-locals` was already reported before this change. The per-item fan-out was
  moved into the module-level `_fan_out()` helper, but the statement count still ended
  at 51/50.
- Verification (py3.11 sandbox): `tox -e py311 -- -k "not forkserver and not spawn"`
  → 704 passed, 10 skipped (×2 runs). `-k "forkserver or spawn"` → 1163 passed,
  20 skipped (×2 runs). bandit: no issues. pylint: 9.88/10, no new messages in the
  touched files.
- **L0 independent review** (2026-09-29): read every diff line-by-line (not just
  the subagent reports), re-ran `tox -e py311` fork-context phase after each
  phase (708 passed after the Q5 fix — exact match with the report), reran
  pylint (9.88/10, unchanged) and bandit (clean) myself, hand-verified the
  `direction` decorator's unhashable-input edge case empirically (confirmed
  `DIRECTION([1,2,3])` still raises `ValueError`, not an uncaught `TypeError`),
  and reviewed `_release_destinations`'s daemon-thread/`cancel_join_thread()`
  interaction against CPython's `multiprocessing.util.Finalize` semantics. No
  changes required beyond the Q5 follow-up requested above. Cleaned up a stray
  empty `throughput_results.txt` artifact left at the repo root by benchmark
  runs (not tracked, not part of the diff).
