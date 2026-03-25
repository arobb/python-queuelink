# Plan: `link()` factory function

## Goal

Provide a single entry point that accepts a source and destination of any
supported type (queue, handle, file path, pipe, Connection) and returns the
correctly wired combination of `QueueLink`, `QueueHandleAdapterReader`, and/or
`QueueHandleAdapterWriter` — so users never need to discover which class to use
or how to connect them.

## Current state

`link()` is fully implemented (v1 complete). See PLAN_PROGRESS.md for the
detailed implementation record and remaining documentation work (steps 15–18).
The description below reflects the original design intent and is preserved for
reference.

## Input types to support

| Type | Detection | Role |
|---|---|---|
| `queue.Queue` and variants | `isinstance(obj, tuple(THREADED_QUEUES))` | source or destination |
| `multiprocessing.Queue` and variants | `isinstance(obj, UNION_MULTIPROCESSING_QUEUES)` | source or destination |
| `multiprocessing.managers.BaseProxy` (Manager queues) | `isinstance(obj, BaseProxy)` and has queue methods (`put`, `get`, `empty`) | source or destination |
| Open file handle / pipe (`IO`) | `isinstance(obj, IOBase)` or has `readline`/`write` | source or destination |
| File path (`str`, `PathLike`) | `isinstance(obj, (str, PathLike))` | source or destination |
| `multiprocessing.connection.Connection` | `isinstance(obj, multiprocessing.connection.Connection)` | source only (destination unsupported for now) |

## Combinations and what they produce

| Source | Destination | Components created |
|---|---|---|
| queue | queue | `QueueLink(source, destination)` |
| queue | [queue, ...] | `QueueLink(source, [destinations])` |
| handle/path | queue | `QueueHandleAdapterReader(queue, handle=source)` |
| queue | handle/path | `QueueHandleAdapterWriter(queue, handle=destination)` |
| handle/path | handle/path | Reader → internal queue → Writer (no QueueLink) |
| handle/path | [mixed] | Fan-out: Reader → internal queue → QueueLink → per-destination queues/writers |
| Connection | queue | `QueueHandleAdapterReader(queue, handle=source)` |
| Connection | [queue, ...] | Reader -> internal queue -> `QueueLink` fan-out to queue destinations |
| Connection | handle/path or mixed destinations including handle/path | `TypeError` (destination-side Connection/handle fan-out from Connection source deferred) |
| QueueLink instance | any | `TypeError` (not accepted as input) |
| any | QueueLink instance | `TypeError` (not accepted as input) |

## Proposed signature

```python
def link(source,
         destination,
         *,
         name: str = None,
         start_method: str = None,
         thread_only: bool = False,
         # Reader-specific
         trusted: bool = False,
         wrap_when: WRAP_WHEN = WRAP_WHEN.NEVER,
         wrap_threshold: int = None,
         # QueueLink-specific
         link_timeout: float = 0.01):
```

`destination` should accept a single object or a list, matching QueueLink's
existing pattern.

Returns an object with `stop()` and `is_alive()` interfaces (see return type
below). The return type class is internal — users interact with it via the
`link()` function, not by constructing it directly.

## Return type

`_LinkResult` is an internal class (not exported in `__init__.py`). Users get
it back from `link()` and use its interface, but never import or construct it.

```python
class _LinkResult:
    def __init__(self):
        self.queue_link: QueueLink = None          # None for simple adapter cases
        self.reader: QueueHandleAdapterReader = None
        self.writers: list = []                    # QueueHandleAdapterWriter instances
        self._internal_queues: list = []           # Queues created internally

    def stop(self):
        """Stop all components in the correct order.

        Order:
        1) close reader adapters (stop upstream producers)
        2) wait for internal upstream queues to drain into downstream stages
        3) stop QueueLink publishers (if present) after drain
        4) close writer adapters (downstream sinks last)
        """
        ...

    def is_alive(self) -> bool:
        """Return True if any managed worker thread/process is alive."""
        ...
```

Notes:
- `_LinkResult.stop()` should call component APIs that exist today:
  `QueueLink.stop()` and adapter `.close()`.
- `_LinkResult` may expose `close()` as an alias to `stop()` for consistency
  with adapter usage patterns.
- For queue->queue links, `_LinkResult` should preserve access to core
  `QueueLink` capabilities by either:
  - exposing `result.queue_link` as the canonical escape hatch, and/or
  - forwarding selected methods (`is_empty`, `is_drained`, `get_metrics`).
- Drain semantics should be best-effort and bounded by timeout(s):
  - wait until internal queues report empty/drained, or
  - time out and proceed with stop to avoid indefinite hangs.

## Classification logic

The core of `link()` is a classifier that inspects each endpoint:

```python
def _classify(obj, role: DIRECTION = None) -> _EndpointKind:
    """Returns _EndpointKind enum (QUEUE, HANDLE, PATH, or CONNECTION).

    Raises TypeError for unsupported types (including QueueLink instances).
    """
```

`_EndpointKind` is a local enum in `link.py`; `DIRECTION` comes from `common`.
An if/elif chain selects the right wiring based on
`(_classify(source), _classify(destination))`.

Classification precedence (to avoid ambiguous matches):
1. Reject `QueueLink` and `_LinkResult` instances
2. queue types (`UNION_SUPPORTED_QUEUES`)
3. `multiprocessing.connection.Connection`
4. path types (`UNION_SUPPORTED_PATH_TYPES`)
5. IO handle types (`IOBase` / object with required methods for role)
6. otherwise `TypeError`

`BaseProxy` safety rule:
- Treat a `BaseProxy` as queue-like only if it exposes queue methods
  (`put`, `get`, `empty`). Otherwise raise `TypeError` early.

Destination normalization:
- Accept `destination` as either a single endpoint or a `list` of endpoints.
- Non-list iterables (`tuple`, `set`, generators) are rejected with `TypeError`
  to keep behavior explicit and deterministic.
- Empty destination lists are rejected with `ValueError`.
- Duplicate destination objects are rejected with `ValueError` (same behavior
  users already see when registering duplicate queues in `QueueLink`).

IO contract checks:
- Source classified as handle must support readable contract (`readline`).
- Destination classified as handle must support writable contract (`write`).
- `flush` is optional; adapters already tolerate handles without it.
- If role-specific contract is missing, raise `TypeError` before dispatch.

Internal queue creation policy:
- All internal queues are created with `ctx = multiprocessing.get_context(start_method)`.
- Default internal queue type is `ctx.Queue()` for portability across
  thread/process paths and start methods.
- Do not use global `multiprocessing.Queue()` constructors.

## Steps

1. **Add type classification helper** in `link.py`: `_classify(obj)` that
   returns `'queue'`, `'handle'`, `'path'`, or `'connection'` based on
   isinstance checks against the existing union types in `common.py`.
   Raises `TypeError` for unrecognized types and for QueueLink instances.

2. **Define `_LinkResult`** class in `link.py` (internal, not exported) to
   hold references and provide `stop()` and `is_alive`.

3. **Implement `link()` dispatch** for the queue→queue case first (simplest:
   just delegates to `QueueLink`). Raise `TypeError` for Connection as
   destination and for QueueLink instances as input.

4. **Add handle/path→queue case**: creates a `QueueHandleAdapterReader`.

5. **Add connection→queue and connection→[queue, ...] cases**:
   `QueueHandleAdapterReader` supports Connection sources today via injected
   `readline`; support queue-only destinations in this iteration.

6. **Add queue→handle/path case**: creates a `QueueHandleAdapterWriter`.

7. **Add handle→handle case**: creates an internal queue, wires
   Reader → internal queue → Writer directly. No QueueLink involved.

8. **Add fan-out support**: when `destination` is a list, classify each
   element individually. If all destinations are queues, use QueueLink
   directly. If source is handle/path and any destination is handle/path,
   create internal queues and writers as needed, with a QueueLink to
   distribute. If source is Connection and any destination is handle/path,
   raise `TypeError` in this iteration.

9. **Export from `__init__.py`**: add `link` only (not `_LinkResult`).

10. **Update AGENTS.md**: update `link.py` description in architecture tree
    (remove "Stub" note), add `link` to public API section, add
    `link_test.py` to test structure tree.

11. **Update docs**: if `link()` warrants a README example, add one showing
    the simplest case (replacing the current multi-step queue wiring with a
    single `link()` call). Update `docs/api.rst` if it references the public
    API.

12. **Tests**: new test file `tests/tests/link_test.py` covering each
    combination. Since `link()` abstracts away queue-type and start-method
    complexity, prefer focused unit/example-style tests (style 2 in
    AGENTS.md) over the full parameterized matrix. Use the matrix only for
    cases where queue type or start method is expected to affect behavior.
    Include `TypeError` tests for unsupported inputs. Add cleanup/lifecycle
    tests that verify workers terminate after `_LinkResult.stop()` for:
    handle->handle, handle->mixed fan-out, and connection->queue cases.
    Add stop-order tests verifying upstream internal queues are drained before
    QueueLink/writer shutdown is finalized.
    Add explicit non-matrix regression tests that run internal-queue paths with
    `start_method in {"spawn", "forkserver"}` to catch SemLock/context issues.
    `context` import is only required if shared path/logging setup is needed.

13. **Validate**: run the full harness validation to confirm everything passes:

    ```bash
    # Tests (single version for fast feedback, then full matrix)
    tox -e py313
    tox

    # Lint
    tox -e pylint
    tox -e bandit

    # Docs build
    tox -e docs
    ```

    All checks must pass before the work is considered complete (see
    HARNESS.md — CI is the feedback loop, same gates for everyone).

## Decisions

Resolved from discussion:

1. **Handle-to-handle wiring**: use Reader → internal queue → Writer directly.
   QueueLink is only introduced when fan-out requires it. The adapters should
   handle simple cases independently and robustly.

2. **Naming**: `link()` remains a module-level factory function. The return
   type (`_LinkResult`) is internal — not exported, not documented as public
   API. Users call `link()` and use `stop()`/`is_alive` on the result.
   `_LinkResult` must keep access to underlying `QueueLink` capabilities via
   `result.queue_link` (and optional method forwarding).

3. **Connection support scope**:
   - Connection as source to queue destinations: supported in this iteration.
   - Connection as destination: raises `TypeError` for now.
   - Connection source to handle/path (or mixed with handle/path): raises
     `TypeError` for now, to keep this release scope bounded.
   Writer-side support is feasible as a follow-up by injecting a `write`-like
   method that calls `send()`/`send_bytes()`, mirroring the reader's `readline`
   injection. `link()` should raise `TypeError` for unsupported combinations.

4. **QueueLink as input**: `link()` does not accept already-constructed
   QueueLink instances as source or destination. Raises `TypeError`. May be
   revisited in a future iteration.

5. **Context-aware internals are mandatory**: any queue/lock/event created by
   `link()` must come from `multiprocessing.get_context(start_method)` (or
   `QueueLink(...).Queue()/Lock()/Event()` helpers), never global
   `multiprocessing.*` constructors.

## Open Questions

All resolved. See PLAN_PROGRESS.md § "Open question resolutions (pre-implementation)"
for the decisions:

1. `_LinkResult` exposes both `stop()` and `close()` (alias).
2. List-only fan-out; tuples/sets raise `TypeError`.
3. `connection → [queue, ...]` fan-out included in v1.
4. Mixed queue + handle fan-out included in v1.
5. `link()` always returns `_LinkResult`, even for queue→queue.
