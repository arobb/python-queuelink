# FEAT-005: Documentation and Naming Clarity — Plan

**Status**: NOT_STARTED — low urgency; can be batched
**Source**: REVIEW-001 items 9, 10, 12, 14
**Files in scope**: `src/queuelink/common.py`, `src/queuelink/queuelink.py`,
`src/queuelink/classtemplate.py`, `src/queuelink/contentwrapper.py`, `docs/`

---

## Items to Address

### Item 9 — `link_timeout` doc/code mismatch (REVIEW-001)

`QueueLink.__init__` defaults `link_timeout=0.01` but a docstring somewhere says 0.1.
Fix: audit all references to `link_timeout` default value and make them consistent.

### Item 10 — SimpleQueue polling latency undocumented (REVIEW-001)

`safe_get()` for `SimpleQueue` types uses a 0.005-second polling cycle. This adds
up to ~5ms latency per item and becomes the bottleneck under high throughput.
Fix: add a note to `QUEUE_TYPE_LIST` in `common.py` and/or the `safe_get()` docstring
explaining the trade-off.

### Item 12 — `ClassTemplate` naming (REVIEW-001)

`classtemplate.py` / `ClassTemplate` is a logging mixin. The name does not convey purpose.
Fix (low urgency): rename to `LoggingMixin` / `logging_mixin.py`. Only do this when
touching the file for another reason, to avoid a change purely for renaming.
Note: this is a potentially broad rename — all subclasses must be updated.

### Item 14 — `ContentWrapper` descriptor pattern undocumented (REVIEW-001)

`ContentWrapper` uses `__setattr__`/`__getattr__` to intercept `.value` access for
transparent disk buffering. This is non-obvious.
Fix: add a brief class docstring note explaining the descriptor interception.

---

## Notes

All items in this feature are doc/comment/naming changes only. No behavior changes.
Can be done in a single pass. Low risk.
