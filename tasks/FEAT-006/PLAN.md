# FEAT-006: Encoding Strategy Consistency — Plan

**Status**: NOT_STARTED — needs scoping before implementation
**Source**: REVIEW-001 items 7, 8
**Files in scope**: `src/queuelink/queue_handle_adapter_reader.py`,
`src/queuelink/queue_handle_adapter_writer.py`, `src/queuelink/writeout.py`,
`src/queuelink/contentwrapper.py`

---

## Items to Address

### Item 7 — Three different encoding strategies (REVIEW-001)

| Location | Approach |
|---|---|
| `QueueHandleAdapterReader.__init__` | `codecs.getreader('utf-8')` wrapping |
| `QueueHandleAdapterWriter.queue_handle_adapter` | `content.encode/decode('utf-8')` inline |
| `writeout.py` | `kitchenpatch.getwriter('utf-8')` |
| `contentwrapper.py` | `kitchenpatch.getwriter/getreader` |

If `kitchenpatch` is required for a specific reason (surrogate chars, byte stream
handling that `codecs` mishandles), that reason should be documented. If not,
the encoding strategy should be unified.

**First step**: Document why `kitchenpatch` is used where it is. If no clear reason
exists, unify on stdlib `codecs`. If there is a reason, add inline comments.

### Item 8 — Binary mode detection fragility (REVIEW-001)

`QueueHandleAdapterWriter.open_location()` decides file mode based on the type of
the first line it receives. If a mixed-encoding stream arrives (text then bytes),
the mode is locked by the first line. A binary line written to a text-mode file
raises `TypeError` without a clear error message.

**Fix options**:
- (a) Document the limitation clearly in the method docstring
- (b) Add a check when mode is already set and incoming type mismatches, raising
  a descriptive error rather than letting `TypeError` propagate from `write()`

---

## Open Questions (resolve before starting)

- Q1: Is `kitchenpatch` required for a specific reason, or is it historical?
  (Check git blame / commit history on `writeout.py` and `contentwrapper.py`)
- Q2: For item 8, document-only fix or add defensive type check?
