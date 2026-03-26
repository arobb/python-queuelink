# FEAT-003: Decisions

## Q1 — Relocate or fix in place?

**Decision**: Move benchmarking code to `benchmarks/` at repo root.

**Why**: Benchmarking utilities are developer tools, not library code. Keeping them in
`src/queuelink/` packages them with the library (inflating install size and exposing
tooling internals as a public API surface). The hardcoded relative SQLite DB path
also creates a write side effect wherever the library is installed.

**How to apply**: `benchmarks/` is excluded from the distribution automatically because
`setup.cfg` uses `[options.packages.find] include=queuelink`. No manifest changes needed.
Lint and security scans (`pylint`, `bandit`) target `src/` only — `benchmarks/` is exempt
by design.

---

## Q2 — Keep SQLite or switch to simpler storage?

**Decision**: Keep SQLite; fix the implementation bugs.

**Why**: SQLite provides flexible ad-hoc querying without requiring a separate analysis
tool. Switching to CSV/JSON would require rewriting query logic every time analysis needs
change. The bugs are fixable (broken SQL syntax, wrong `len()` check) without rethinking
the design.

**How to apply**: Fix the three SQLite bugs in `throughput_results.py` and make the DB
path configurable. Do not introduce additional storage formats or change the schema.

---

## Q3 — Include handle-adapter benchmarks?

**Decision**: Yes — add `Throughput_QueueHandleAdapterReader` and
`Throughput_QueueHandleAdapterWriter`.

**Why**: The adapter classes (`QueueHandleAdapterReader`, `QueueHandleAdapterWriter`)
are a significant part of the public API and have different performance characteristics
than the queue-to-queue path (subprocess I/O, file handle overhead). Leaving them
unmeasured creates a blind spot. The scaffolding (`content_dir`, `sample_command_path`)
already exists in `Throughput.__init__`, indicating this was intended from the start.

**How to apply**: Implement in Phase 4, after the core fixes in Phases 2–3 are stable.
Results are stored in the same SQLite session so all benchmark types appear together.
