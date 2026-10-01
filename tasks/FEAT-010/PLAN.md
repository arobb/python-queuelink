# FEAT-010: Core Correctness Fixes and Publisher Wait/Shutdown Strategy

**Status**: NOT_STARTED
**Owner**: None
**Created**: 2026-09-28
**Source**: REVIEW-002 items 1–6, 22, 24

---

## Problem

Several correctness bugs in `QueueLink`, the publisher loop, and the writer adapter,
four of them reproduced:

1. **Publisher cannot stop while blocked on a full destination.** `dest_queue.put(line)`
   has no timeout, so a bounded, unconsumed destination blocks the publisher forever.
   `_stop_publisher` loops on `join(timeout=1)` indefinitely; `register_queue(TO)` and
   `unregister_queue` hang too because they stop all publishers first.
2. **Writer `flush()` calls `os.fsync` on pipes** → `OSError: [Errno 22] Invalid
   argument` on Linux; the worker dies after the data was written.
3. **`get_queue(int)` / `is_empty(int)`** raise `KeyError` for source queues (int vs
   `str` keys).
4. **`close()` uses `if self.started:`** — always true for an Event.
5. **`_publisher` busy-loops on `EOFError`** — no `return`.
6. **`direction` as a str** raises `TypeError` on 3.9–3.11, is accepted on 3.12+
   (`Enum.__contains__` semantics changed).

Plus polling behavior (REVIEW-002 item 22): the default 10 ms `link_timeout` causes
~100 idle wakeups/sec per publisher. It does not add message latency — `get(timeout=)`
returns as soon as an item arrives — it only governs stop responsiveness.

---

## Approach

### Phase 1 — Small fixes (items 2–6)

- **Writer fsync**: in `queue_handle_adapter_writer.flush()`, wrap `os.fsync` and
  ignore `OSError` whose `errno` is `EINVAL` or `ENOTSUP`/`EOPNOTSUPP` (pipes, sockets,
  ttys). Re-raise other errors. Alternative: only fsync when
  `stat.S_ISREG(os.fstat(fd).st_mode)`. Either is fine; the errno approach is more
  permissive of odd-but-fsyncable handles.
- **Int IDs**: normalize `queue_id = str(queue_id)` at the top of `get_queue`,
  `is_empty`, and anywhere else that tests membership (`unregister_queue` already
  normalizes). Also guard `unregister_queue(FROM)` against unknown IDs
  (`publisher_stops.pop` raises `KeyError` today).
- **Event truthiness**: `if self.started is not None and self.started.is_set():` in
  `QueueLink.close()` and `_QueueHandleAdapterBase.close()`.
- **EOFError**: `return` from `_publisher` in the `except EOFError` branch, after
  emitting final metrics (same as the stop path).
- **Direction**: in `validate_direction`, accept a `DIRECTION` member or its string
  value; convert str via `DIRECTION(value)` and rebind into the call; raise
  `ValueError` with a message naming both valid values for anything else. See Q1.

### Phase 2 — Publisher wait/shutdown strategy (items 1, 22)

Put side (the "polling when necessary" case — a sentinel cannot reach a publisher
blocked on `put`):

```python
def _put_until_stopped(dest_queue, item, stop_event, timeout):
    """Returns True if put succeeded, False if stop was requested first."""
    while True:
        try:
            dest_queue.put(item, timeout=timeout)
            return True
        except Full:
            if stop_event.is_set():
                return False
        except TypeError:
            # multiprocessing.SimpleQueue.put() takes no timeout; it only blocks
            # on the pipe write, not on a maxsize, so a plain put is acceptable.
            dest_queue.put(item)
            return True
```

- Decide the semantics of a partial fan-out on stop: if destination A received the
  item and B is full when stop is requested, B misses it. See Q2.
- `task_done()` on the source should only be called after the item was delivered to
  all destinations (or explicitly abandoned per Q2).

Get side:

- Raise the default `link_timeout` from 0.01 to a value in the 0.1–0.25 s range
  (see Q3). Update the README "Tuning link_timeout" section — the current text
  implies the timeout affects throughput/responsiveness under load, which should be
  re-verified with `benchmarks/` before and after.
- No get-side sentinel for now. Rationale (record in DECISIONS.md): the sentinel
  enters a queue QueueLink does not own (other readers may take it), must order
  correctly in Priority/Lifo queues, can block on a full source, and needs a
  per-generation token to avoid stopping a restarted publisher (identity is lost
  across pickling).

`multiprocessing.SimpleQueue`:

- Keep the polling loop in `safe_get` as the fallback.
- Optionally use `multiprocessing.connection.wait([q._reader], timeout)` to block
  without sleeping. This relies on a private attribute; if adopted, guard with
  `getattr(q, '_reader', None)` and fall back to polling. See Q4.
- Correct the `safe_get` docstring: `queue.SimpleQueue.get()` supports `timeout=`
  (3.7+); only `multiprocessing.SimpleQueue` takes the polling path.

### Phase 3 — Regression tests (item 24)

One test per reproduced bug, each failing before its fix:

| Bug | Test sketch |
|-----|-------------|
| Full destination hang | `queue.Queue()` → `queue.Queue(maxsize=1)`; put 3; `stop()` in a thread; assert joined within 3 s. Repeat for process queues with each start method. Also `register_queue(TO)` on a blocked link returns. |
| Writer fsync on pipe | `Popen(['cat'], stdin=PIPE, stdout=PIPE, text=True)`; `QueueHandleAdapterWriter(thread_only=True)`; put a line; wait > 1 s (flush timer); `close()`; assert no thread exception (use `threading.excepthook` capture or pytest's unhandled-thread-exception warning as error) and `cat` output matches. |
| Int ID | `sid = ql.read(q)`; `assert ql.get_queue(int(sid)) is q`; same for `is_empty(int(...))`. |
| EOFError | Destination that raises `EOFError` on `put`; assert publisher exits (not alive) within a bound. |
| Direction str | `register_queue(q, "source")` behaves identically on all matrix versions (accepted or `ValueError`, per Q1). |

### Phase 4 — Docs reconciliation

- README "Tuning link_timeout" updated with new default and the latency clarification.
- `safe_get` docstring corrected.
- `CHANGELOG.rst` Unreleased: Fixed (items 1–6), Changed (default `link_timeout`).

---

## Open Questions

**Q1**: Should `direction` accept the string values `"source"` / `"destination"`, or
only `DIRECTION` members (rejecting strings with `ValueError`)? Accepting is friendlier;
rejecting keeps one spelling.

**Q2**: On stop with a partially delivered fan-out item (some destinations received it,
one is full), should the publisher (a) abandon the remaining destinations, (b) keep
retrying the remaining destinations until a hard deadline, or (c) re-queue nothing and
log a warning with the count of undelivered destinations? (a)+(c) is simplest; (b)
gives better delivery at the cost of shutdown time.

**Q3**: New default `link_timeout`: 0.1 s or 0.25 s? Also: should the put-side retry
timeout reuse `link_timeout` or be a separate parameter?

**Q4**: Adopt `connection.wait([q._reader])` for `multiprocessing.SimpleQueue`, or keep
pure polling to avoid private attributes?

**Q5** (raised by the Phase 2 implementer on 2026-09-29; not resolved): a process publisher
whose `multiprocessing.Queue`/`JoinableQueue` destination is *unbounded* but not being read
still hangs `stop()`. Its `put()` never raises `Full`, so `_put_until_stopped` returns
right away. Once more data is queued than the OS pipe buffer holds, though, the child
publisher cannot exit. At exit, `multiprocessing` joins the queue's feeder thread, and that
join waits for every buffered item to be written to the pipe. This was reproduced with fork,
200 × 10 KB items and nobody reading the destination: `stop()` was still blocked after 8 s
and the child process had to be killed. This is not item 1's bounded-`Full` case, and the old
code hung here too. It is a related liveness gap, though. Options:
(a) have a stopping publisher call `dest_queue.cancel_join_thread()` on multiprocessing
queue destinations, which drops items still sitting in the feeder buffer;
(b) bound `_stop_publisher`'s join, then `terminate()` the process with a warning;
(c) document it as a limitation (read your destinations, or bound them with `maxsize`).
(a) and (b) trade delivery for liveness the same way Q2 does. There is a related case with
`multiprocessing.SimpleQueue`. It has no feeder thread, so its `put()` blocks directly on a
full pipe instead (see DECISIONS.md, "Detecting `put(timeout=)` support"); only (b) would
cover that case.

---

## Files

- `src/queuelink/queuelink.py` — Phases 1, 2
- `src/queuelink/common.py` — Phase 2 (`safe_get`)
- `src/queuelink/queue_handle_adapter_writer.py` — Phase 1 (fsync)
- `src/queuelink/queue_handle_adapter_base.py` — Phase 1 (`close()`)
- `tests/tests/queuelink_test.py`, `tests/tests/queuelink_safe_get_test.py`,
  `tests/tests/queuelink_handle_adapter_writer_test.py` — Phase 3
- `README.rst`, `CHANGELOG.rst` — Phase 4

## Dependencies

None. Can start immediately. Should land before FEAT-011 (FEAT-011 changes the
publisher's put path to clone ContentWrappers; easier on top of the new put helper).
