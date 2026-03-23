# FEAT-001: link() Factory Function - Task Breakdown

## Phase 1: Core Implementation ✅ COMPLETE

- [x] Design and architecture (see PLAN.md)
- [x] Implement `_classify()` helper with enum-based classification
- [x] Implement `_LinkResult` class with proper lifecycle methods
- [x] Implement `link()` function with all dispatch patterns
- [x] Export from `__init__.py`
- [x] Write comprehensive tests (32 tests, all passing)
- [x] Validate AGENTS.md compliance (enums, no @property misuse, specific exceptions)
- [x] Initial api.rst update (autofunction directive)

## Phase 2: Documentation 🔄 IN PROGRESS

**Dependencies**: Phase 1 complete

### Tasks

| ID | Description | Status | Owner | Files |
|----|-------------|--------|-------|-------|
| DOC-1 | Update README.rst with link() examples | TODO | - | README.rst |
| DOC-2 | Create docs/link_guide.rst | TODO | - | docs/link_guide.rst |
| DOC-3 | Update docs/index.rst with link_guide | TODO | - | docs/index.rst |
| DOC-4 | Validate rendered docs build | TODO | - | - |

### DOC-1: Update README.rst

Replace simple QueueLink examples with `link()` where appropriate:
- Update "Use" section to lead with `link()` as primary API
- Show simple queue→queue example with `link()`
- Move existing QueueLink examples to "Advanced Usage" or "Direct QueueLink Usage"
- Add `link()` examples for common patterns (file→queue, queue→file, fan-out)
- Keep QueueLink examples for when direct control is needed

### DOC-2: Create docs/link_guide.rst

Comprehensive usage guide:
- Getting started (basic queue→queue)
- Supported endpoint types (queues, files, handles, Connections)
- Fan-out patterns (single→multiple, mixed types)
- Result interface (`stop()`, `close()`, `is_alive()`)
- Advanced parameters (`start_method`, `thread_only`, `wrap_when`)
- Error handling (TypeError/ValueError cases)
- When to use `link()` vs direct classes
- Migration guide from direct QueueLink usage

### DOC-3: Update docs/index.rst

- Add link_guide.rst to toctree after api.rst
- Update introductory text to mention `link()` as recommended API
- Add quick example using `link()` in the index intro

### DOC-4: Validate rendered docs

- Run `tox -e docs` to build
- Verify all code blocks have correct syntax highlighting
- Check that autofunction picks up `link()` signature and docstring
- Ensure cross-references work (links to QueueLink, WRAP_WHEN, etc.)
- Visual inspection: examples are clear and properly formatted

## Phase 3: Future Enhancements (v2+)

See PROGRESS.md for planned iterations:
- v2: Automatic wrap/unwrap based on destination capabilities
- v3: Additional optimizations and queue-type specific tuning

## Completion Criteria

- [ ] All Phase 2 tasks marked DONE
- [ ] Documentation builds without warnings
- [ ] All tests passing (32/32)
- [ ] Pylint ≥ 9.8/10
- [ ] No AGENTS.md violations
