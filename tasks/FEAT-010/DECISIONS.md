# FEAT-010 Decisions

Resolved by L0 orchestrator before dispatching implementation subagents, per
PROGRESS.md checklist item "Resolve open questions Q1–Q4 in PLAN.md".

## Q1 — `direction` as a string

**Decision**: Accept both `DIRECTION` members and their string values.
`validate_direction` converts a `str` via `DIRECTION(value)` and rebinds it
into the call; anything else raises `ValueError` naming both valid values
(`"source"`/`"destination"`). This matches PLAN.md's Phase 1 approach text
and keeps backward compatibility for any caller that relied on the
(accidental) 3.12+ acceptance, while making the behavior version-independent
and giving a clear error instead of a version-dependent `TypeError`.

## Q2 — Partial fan-out on stop

**Decision**: (a)+(c) — on `stop()`, the publisher abandons any destination
still full/blocked and logs a warning naming the destination id and the count
of undelivered destinations. No retry-until-deadline (b). Rationale: the bug
being fixed is a liveness bug (`stop()` must terminate); this library does not
claim delivery guarantees anywhere else (see REVIEW-002 item 22's rationale
for skipping a get-side sentinel), so trading delivery guarantees for bounded
shutdown time is consistent with the existing design, not a regression in a
guarantee QueueLink ever made.

## Q3 — New default `link_timeout`

**Decision**: `0.1` s (100 ms), reusing the same value for the put-side retry
timeout — no new constructor parameter. Rationale: a 10x reduction in idle
wakeups vs. the current 10 ms default, while keeping worst-case `stop()`
latency low enough (~100 ms) that it should not be user-visible. `0.25` s was
considered but rejected as an unnecessary latency/throughput-risk trade for
marginally fewer wakeups; re-verify with `benchmarks/` before finalizing (see
010-2-3/010-2-4).

## Q4 — `connection.wait()` for `multiprocessing.SimpleQueue`

**Decision**: Defer. Do not adopt `multiprocessing.connection.wait([q._reader], timeout)`
in this feature. Rationale: relies on a private, undocumented attribute
(`_reader`) that is not guaranteed stable across Python versions/implementations;
the task board already marks this optional (010-2-5). Keep pure polling in
`safe_get`, just with the docstring corrected (010-2-6) to say only
`multiprocessing.SimpleQueue` — not `queue.SimpleQueue` — takes the polling
path. Revisit only if idle-CPU benchmarks after the `link_timeout` bump still
show a problem worth the fragility.

## No get-side stop sentinel (010-2-7)

**Decision**: Do not stop publishers by putting a sentinel into their source
queue; they keep using a bounded `get(timeout=link_timeout)` and re-check
`stop_event` between attempts. Rationale (from PLAN.md, Phase 2 "Get side"):

- The sentinel would enter a queue QueueLink does not own. Other readers of
  that queue, including other QueueLink instances, could take it, which would
  stop the wrong consumer or leave a stray marker in their data.
- It would have to be ordered correctly in `PriorityQueue`/`LifoQueue`
  sources. A LIFO or priority order can put it ahead of, or behind, items that
  should be handled first.
- Putting the sentinel can itself block when the source is bounded and full,
  which is the same kind of hang this feature fixes.
- It would need a per-generation token so a sentinel left over from an earlier
  stop does not stop a publisher restarted later by `register_queue(TO)` or
  `unregister_queue`. Object identity does not survive pickling across process
  queues, so a plain `object()` sentinel cannot work as that token.

A sentinel also could not help the put side. A publisher blocked in `put()` to
a full destination never reads its source, so it would never see the
sentinel. That case needs the bounded, retrying put (`_put_until_stopped`)
anyway. With `link_timeout` at 0.1 s (Q3), polling on the get side costs about
10 wakeups per second per idle publisher, which does not justify the added
complexity.

## Detecting `put(timeout=)` support by signature, not `TypeError` (010-2-1)

**Decision**: PLAN.md's `_put_until_stopped` sketch falls back to a plain
`put(item)` on `TypeError`. The implementation instead checks once per
destination, using `inspect.signature(q.put).bind(item, timeout=...)`, whether
`put()` accepts `timeout=`. The result is cached for the rest of the publisher
run. Only `multiprocessing.SimpleQueue` fails this check. Manager proxies take
`*args, **kwargs` and pass it. Callables with no introspectable signature are
assumed to accept `timeout=`.

Rationale: `put()` can raise `TypeError` for other reasons. Examples are an
unorderable item in a `PriorityQueue`, or an unpicklable item sent through a
manager proxy. Retrying those as an unbounded `put()` would re-raise the error
at best. On a full bounded queue it would block forever and bring back the
hang this feature fixes.

Known residual limitation: `multiprocessing.SimpleQueue` is unbounded, but its
`put()` blocks on the pipe write once the OS pipe buffer (~64 KiB on Linux)
fills and nobody reads. A publisher blocked there still cannot be stopped.
Fixing that would need private attributes (the same objection as Q4), so it is
out of scope.

## Q5 — Unbounded, unread `multiprocessing.Queue`/`JoinableQueue` destination hangs process exit

**Decision**: Fix with option (a) — `cancel_join_thread()` on the destination.
Rationale: unlike Q4's `connection.wait([q._reader])`, `cancel_join_thread()` is
public, documented `multiprocessing.Queue`/`JoinableQueue` API, made for exactly
this situation (it exists to let a process exit without its feeder thread
finishing a flush of unconsumed buffered items). It's a small, low-risk change
directly in the spirit of Q2 (trade delivery for liveness on shutdown, log what
was dropped), not a new design. Option (b) (bound the join, then `terminate()`
the process) is a materially larger change — forcibly killing a process has its
own hazards — for a narrower benefit, and isn't warranted alongside (a). Option
(c) (leave it undocumented) isn't acceptable on its own: this is the exact
"join-before-consume deadlock" class of issue REVIEW-002 item 17 already
identifies as inherent to `multiprocessing.Queue`.

**Implementation note (added after building it)**: plain `cancel_join_thread()`
on every destination at every exit point — as first decided above — turned out
to drop items on the *normal* shutdown path, not just the abandoned-on-stop
path: it discards whatever is still sitting in the feeder thread's send buffer
when the process exits, including items already handed to a destination that
has an active reader keeping up just fine. It also isn't safe for a thread
publisher, which shares the *caller's* queue objects — cancelling their join or
closing them would break the caller's own later use of that queue. The
implementation (`_release_destinations` in `queuelink.py`) is therefore a
bounded flush before the cancel, and only for process publishers: each
destination gets `close()` + a background `join_thread()` with a shared
`link_timeout` deadline; only a destination still unflushed at the deadline
gets `cancel_join_thread()`, with a warning naming it. A thread publisher
returns immediately without touching its destinations at all (detected via
`current_thread() is not main_thread()` — a process publisher's target runs on
that process's main thread; a thread publisher never does). Verified with
repeated runs: the naive version lost items in ~2 of 10 runs of a
3000-item/read-destination probe; the bounded-flush version delivered
3000/3000 across repeated runs, and a dedicated test
(`QueueLinkThreadPublisherLeavesDestinationOpenTest`) confirms a thread
publisher's destination is left open and usable by the caller after `stop()`.

Scope: this fixes the `multiprocessing.Queue`/`JoinableQueue`-family case only,
where a feeder thread does the buffering. It does **not** fix the separate,
narrower `multiprocessing.SimpleQueue` case noted above (no feeder thread; the
`put()` call itself blocks directly on a full OS pipe) — that one has no public
API equivalent to `cancel_join_thread()` and would need option (b) alone.
Documented as a known limitation, not fixed here; revisit only if it proves to
matter in practice (an unbounded, unread `SimpleQueue` destination filled past
one OS pipe buffer is an unusual usage pattern).
