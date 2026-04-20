# FEAT-009: Writer Adapter Binary Mode Detection

**Status**: NOT_STARTED
**Owner**: None
**Created**: 2026-04-20
**Source**: REVIEW-001 item 8

---

## Problem

`QueueHandleAdapterWriter.queue_handle_adapter` determines whether to open a
path-based handle in binary or text mode by inspecting the *first line*
dequeued from the source:

```python
def open_location(location, line):
    if hasattr(line, 'decode'):   # bytes → binary mode
        return open(location, mode='w+b')
    return open(location, mode='w+')  # str → text mode
```

FEAT-006 added `TypeError` guards so that if a subsequent line's type disagrees
with the mode chosen by the first line the worker raises immediately rather than
silently corrupting the file. That was an improvement, but four concerns remain:

1. **Terminal, unrecoverable failure.** The `TypeError` propagates out of the
   `while True` loop and is not caught anywhere in the adapter. The worker
   process or thread dies without draining the queue or signalling the caller.
   Any items still in the queue are lost. The caller can only detect the failure
   by noticing the adapter has stopped unexpectedly.

2. **Non-deterministic failure under concurrent producers.** If multiple
   producers write to the same queue with different line types (bytes vs str),
   which mode gets selected depends on which line arrives first. This is a
   race-sensitive invariant with no caller-visible way to enforce it up front.

3. **No pre-declaration of intended mode.** A caller who knows in advance
   whether the stream will be binary or text has no way to communicate that.
   There is no `mode` parameter — the only option is to ensure the first line
   has the correct type.

4. **`.mode` attribute assumed on all handles.** When `handle` is a pre-opened
   object rather than a path, the code reads `'b' in handle.mode` on every loop
   iteration. Not all `io`-compatible objects expose `.mode` (notably
   `io.BytesIO` and `io.StringIO` do not). An `AttributeError` here would also
   kill the worker without a clear message. The mode is also immutable once a
   file is opened, so re-reading it every iteration is unnecessary.

---

## Approach

### Phase 1 — Determine handle mode once, at the right moment

Move the `is_handle_bin` assignment out of the `while True` loop body. It
should be set exactly once, immediately when the handle becomes ready:

- For **pre-opened handles** (path was not a string/`PathLike`): set
  `is_handle_bin` immediately after the `if isinstance(handle,
  get_args(UNION_SUPPORTED_PATH_TYPES))` block, before entering the loop.
- For **lazy-opened handles** (path string/`PathLike`): set `is_handle_bin`
  immediately after `handle = open_location(handle_name, line)` returns, before
  the existing type-guard checks.

Remove the `is_handle_bin = 'b' in handle.mode` line from the loop body.

### Phase 2 — Replace `.mode` sniffing with `isinstance` checks

Use `isinstance(handle, (io.RawIOBase, io.BufferedIOBase))` to detect binary
handles. This covers all standard `io` module types:

- `io.BufferedWriter` / `io.FileIO` (from `open(..., 'wb')`) → binary
- `io.BytesIO` → binary
- `io.TextIOWrapper` (from `open(..., 'w')`) → text
- `io.StringIO` → text

These checks work without a `.mode` attribute and do not read any mutable state
on the handle object. Use this both for pre-opened handles (Phase 1 setup
before the loop) and for lazy-opened handles (immediately after
`open_location()` returns — `open()` always returns a standard `io` type so
`.mode` is available there, but `isinstance` is still preferred for
consistency).

### Phase 3 — Add a `mode` parameter

Add an optional `mode: str = None` parameter to `QueueHandleAdapterWriter.__init__`
and thread it through `queue_handle_adapter` to `open_location`. When `mode` is
supplied, `open_location` uses it directly; when absent, the `isinstance`-based
inference from the first line is the fallback.

This gives callers who know their stream type a deterministic option that does
not depend on first-line inference.

### Phase 4 — Catch `TypeError` cleanly

Wrap the mixed-type `TypeError` inside the loop. On catch: log the error with
the offending line's type and the handle's expected mode, set the stop event,
and `break` to let the worker exit cleanly. This ensures the queue is not
abandoned mid-stream and the caller can detect the stop via `is_alive()`.

### Phase 5 — Tests and docs reconciliation

Add explicit tests covering:
- A pre-opened `io.BytesIO` handle (no `.mode` attribute) works correctly
- A pre-opened `io.StringIO` handle works correctly
- A mixed-type stream (bytes after text, or text after bytes) stops the worker
  cleanly via the `TypeError` path rather than crashing it
- A path-based handle with an explicit `mode` argument uses the declared mode
  regardless of first-line type

Update the `QueueHandleAdapterWriter` docstring to document the `mode`
parameter. Verify `docs/api.rst` renders correctly (`autoclass :members:`
picks up the docstring automatically).

---

## Open Questions

**Q1**: Should `mode` accept the full `open()` mode string (e.g. `'w+b'`,
`'w+'`) or a simpler `'binary'`/`'text'` enum? Using the `open()` string is
familiar but exposes `open_location` internals; an enum is cleaner but adds
a new public type.

*A1*: Writer can output to several destinations with different behaviors. At this
juncture, an enum seems simpler.

**Q2**: Should the clean `TypeError` catch in Phase 4 re-raise after logging
(so the caller sees it in e.g. `proc.exitcode`) or just set the stop event and
exit silently? Silent exit is easier for callers to handle via `is_alive()`,
but loses the exception context in process-based publishers.

*A2*: Re-raise after logging (and any other handling).

---

## Files

- `src/queuelink/queue_handle_adapter_writer.py` — all phases
- `tests/tests/queuelink_handle_adapter_writer_test.py` — Phase 5

## Dependencies

None. Can start immediately.
