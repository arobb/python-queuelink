# Implementation Progress: `link()` factory function

## ✅ COMPLETED — v1 (basic functionality)

All steps completed and validated. See git history for implementation.

### Open question resolutions (pre-implementation)

1. **`stop()` and `close()`**: expose both — `close()` as alias for `stop()`.
2. **Tuple destinations**: list only; tuples rejected with `TypeError`.
3. **Connection→[queue,...] fan-out**: included (user confirmed).
4. **Mixed queue+handle fan-out**: included per combinations table.
5. **Return type**: always `_LinkResult`, even for queue→queue.

### Completed steps

- [x] 1. `_classify()` helper
- [x] 2. `_LinkResult` class
- [x] 3. `link()` — queue→queue dispatch + TypeError guards
- [x] 4. handle/path→queue
- [x] 5. connection→queue and connection→[queue,...]
- [x] 6. queue→handle/path
- [x] 7. handle→handle (direct, no QueueLink)
- [x] 8. fan-out support
- [x] 9. Export `link` from `__init__.py`
- [x] 10. Update AGENTS.md
- [x] 11. Update api.rst with autofunction directive
- [x] 12. Tests (`link_test.py`)
- [x] 13. Validate (tox py313, full tox, pylint, bandit, docs)
- [x] 14. Strict AGENTS.md compliance (enums, no @property misuse, specific exceptions)
- [~] 15. **Update README.rst**: README already leads with `link()`, has basic queue→queue
  and fan-out examples, and notes when to use `QueueLink` directly. Remaining:
  - Add `link()` examples for handle/file-sourced patterns (file→queue, queue→file)
  - Note: QueueLink examples live in `docs/index.rst`, not README — "move to Advanced
    Usage" sub-goal is moot for README
- [ ] 16. **Create docs/link_guide.rst**: Comprehensive usage guide with all patterns
  - Getting started (basic queue→queue)
  - Supported endpoint types (queues, files, handles, Connections)
  - Fan-out patterns (single→multiple, mixed types)
  - Result interface (`stop()`, `close()`, `is_alive()`)
  - Advanced parameters (`start_method`, `thread_only`, `wrap_when`)
  - Error handling (TypeError/ValueError cases)
  - When to use `link()` vs direct classes (`QueueLink` is not deprecated — use it
    when you need runtime queue registration, metrics, or fine-grained lifecycle control)
  - ~~Migration guide~~ — do not frame as migration; `link()` is additive, not a replacement
- [ ] 17. **Update docs/index.rst**: Current intro is entirely QueueLink-centric with no
  mention of `link()`; toctree only contains `api`
  - Add link_guide.rst to toctree after api.rst
  - Update introductory text to present `link()` as the recommended starting point
  - Add a brief `link()` quick-start example before the existing QueueLink examples
- [ ] 18. **Validate rendered docs**: Build with sphinx and verify examples render correctly
  - Run `tox -e docs` to build
  - Verify all code blocks have correct syntax highlighting
  - Check that autofunction picks up `link()` signature and docstring
  - Ensure cross-references work (links to QueueLink, WRAP_WHEN, etc.)
  - Visual inspection: examples are clear and properly formatted

### Usage Documentation (v1)

The `link()` factory function is the recommended way to connect sources and destinations. It automatically selects and wires the correct components based on endpoint types.

#### Basic Usage

```python
import queue
from queuelink import link

# Queue to queue
src = queue.Queue()
dst = queue.Queue()
result = link(src, dst)

src.put("hello")
print(dst.get())  # "hello"

result.stop()  # Clean shutdown
```

#### Supported Endpoints

**Sources**:
- Any queue type (queue.Queue, multiprocessing.Queue, Manager().Queue(), etc.)
- File paths (str or PathLike)
- Open file handles (must have `.readline()`)
- Subprocess pipes (e.g., `Popen(..., stdout=PIPE)`)
- `multiprocessing.connection.Connection` (to queue destinations only)

**Destinations**:
- Any queue type
- File paths (str or PathLike)
- Open file handles (must have `.write()`)
- **List of any of the above** for fan-out (e.g., `[queue1, queue2, "output.txt"]`)

#### Fan-out Examples

```python
# Queue to multiple queues
result = link(src, [dst1, dst2, dst3])

# File to queue and file (mixed fan-out)
result = link("input.txt", [output_queue, "output.txt"])

# Queue to queues and files
result = link(src, [queue1, queue2, "log.txt", "backup.txt"])
```

#### Result Interface

`link()` returns a `_LinkResult` object with:

- **`stop()`**: Shutdown in correct order (reader → drain → publishers → writers)
- **`close()`**: Alias for `stop()` (consistent with adapter API)
- **`is_alive()`**: Returns `True` if any worker thread/process is running
- **`queue_link`**: Direct access to underlying `QueueLink` (queue→queue only)
- **`reader`**: The `QueueHandleAdapterReader` instance (if created)
- **`writers`**: List of `QueueHandleAdapterWriter` instances (if created)

#### Advanced Usage

```python
# Control multiprocessing start method
result = link(src, dst, start_method='spawn')

# Force threading (no separate processes)
result = link(src, dst, thread_only=True)

# Named components for logging
result = link(src, dst, name="my_pipeline")

# Content wrapping for large messages (file/pipe sources)
from queuelink import WRAP_WHEN
result = link("input.txt", dst, wrap_when=WRAP_WHEN.ALWAYS)

# Access underlying QueueLink for metrics
result = link(src, dst)
if result.queue_link:
    metrics = result.queue_link.get_metrics()
```

#### Error Handling

```python
from queuelink import link

# TypeError: Connection destinations not supported
conn_recv, conn_send = multiprocessing.Pipe()
result = link(src, conn_recv)  # Raises TypeError

# TypeError: Tuples/sets not accepted (use list)
result = link(src, (dst1, dst2))  # Raises TypeError
result = link(src, [dst1, dst2])  # OK

# ValueError: Empty destination list
result = link(src, [])  # Raises ValueError

# ValueError: Duplicate destinations
result = link(src, [dst, dst])  # Raises ValueError
```

#### When to Use Direct Classes Instead

Use `QueueLink` directly when you need:
- Dynamic queue registration/unregistration at runtime
- Fine-grained control over publisher lifecycle
- Access to queue metrics and drain checking
- To avoid `_LinkResult` wrapper overhead

Use adapters directly when you need:
- Custom error handling during read/write
- Direct control over content wrapping thresholds
- Non-standard multiprocessing context handling

---

## 🔜 NEXT ITERATION — v2 (automatic wrap/unwrap)

**Goal**: Intelligently apply `ContentWrapper` wrap/unwrap based on destination capabilities.

### Design decisions needed

1. **Wrap detection strategy**:
   - When any destination is a file/path (unbounded), auto-enable wrapping on readers?
   - Default `wrap_when=WRAP_WHEN.AUTO` when file destinations present?
   - Override: allow user to force `WRAP_WHEN.NEVER` or `WRAP_WHEN.ALWAYS`

2. **Unwrap strategy**:
   - Currently `QueueHandleAdapterWriter` unwraps automatically
   - Does this need enhancement or is current behavior sufficient?
   - Should queue-to-queue paths check destination characteristics?

3. **Mixed destination handling**:
   - queue → [file, file]: wrap enabled (all destinations unbounded)
   - queue → [queue, file]: wrap enabled? (mixed bounded/unbounded)
   - Principle: safe default = wrap when *any* destination is unbounded

4. **Threshold selection**:
   - Current default: wrap_threshold not set (rely on WRAP_WHEN setting)
   - Auto mode: could inspect queue types and set reasonable defaults
   - E.g., multiprocessing queues → lower threshold due to pickling overhead

### Proposed steps

- [ ] 1. Design: finalize wrap/unwrap heuristics (see questions above)
- [ ] 2. Implement: `_should_enable_wrapping(destinations, dest_kinds)` helper
- [ ] 3. Implement: auto-wrap logic in `link()` dispatch paths
- [ ] 4. Update: `link()` docstring to document automatic wrapping behavior
- [ ] 5. Tests: verify auto-wrap with file destinations
- [ ] 6. Tests: verify unwrap on file writes
- [ ] 7. Tests: verify user override (`wrap_when=WRAP_WHEN.NEVER`)
- [ ] 8. Update: README with auto-wrap examples
- [ ] 9. Update: AGENTS.md only if new multiprocessing pitfalls are discovered
  during implementation (design notes are not AGENTS.md material)
- [ ] 10. Validate: full test suite + linters

### Open questions (to resolve before implementation)

- **Q1**: Should auto-wrap be enabled for *any* file destination, or only when *all* destinations are files?
  - **Recommendation**: Enable when *any* destination is a file (safer default, prevents queue bloat)

- **Q2**: What should the default `wrap_threshold` be in auto mode?
  - **Recommendation**: Use `ContentWrapper` defaults (rely on `WRAP_WHEN.AUTO` logic)

- **Q3**: Should we inspect queue types to tune thresholds?
  - **Recommendation**: Defer to v3; v2 uses simple "file present → enable AUTO" logic
