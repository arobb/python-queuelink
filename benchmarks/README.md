# Benchmarks

This directory contains throughput benchmarks for the `queuelink` library. These are
developer tools for measuring latency and throughput — they are **not** run in CI.

## Contents

| File | Purpose |
|------|---------|
| `throughput.py` | Benchmark classes: `Throughput_QueueLink`, `Throughput_QueueHandleAdapterReader`, `Throughput_QueueHandleAdapterWriter` |
| `throughput_results.py` | SQLite-backed result storage; run as `__main__` to print latest session results |
| `throughput_test_exclude.py` | Parameterized test runner (excluded from CI collection by `_test_exclude.py` suffix) |
| `context.py` | Path bootstrap — imported for its side effect of adding `benchmarks/` to `sys.path` |
| `content/line_output.py` | Helper script that writes N lines to stdout; used as a subprocess fixture |
| `throughput/throughput.sqlite.db` | Results database (created on first run, not committed) |

---

## When to run benchmarks

Throughput benchmarks are developer tools for three specific scenarios:

### 1. Pre-release baseline capture

Run the full benchmark suite before tagging a release to establish a performance baseline
for that version. Store or note the session ID alongside the tag. Future changes can then
be compared against this baseline.

### 2. Change validation

Run before **and** after any change suspected to affect throughput — for example, changes
to `queuelink.py`'s publisher loop, `safe_get()`, or the adapter I/O path. Compare the
two sessions in the SQLite database to see whether the change helped, hurt, or was neutral.

### 3. Environment profiling

Run on a new machine or Python version to establish what to expect for that environment.
The `host_info` table (see below) records the hardware context alongside every result.

---

## Why NOT in CI

The benchmarks are intentionally excluded from continuous integration:

- **CI runners are not controlled environments.** Available CPU, load, and OS configuration
  vary run to run — results are not comparable across runs.
- **The full matrix is slow.** 9 queue types × 3 start methods × 5 rounds × 3 test functions
  for `QueueLink` alone is a large number of parameterized test cases, each involving
  subprocess creation and inter-process communication.
- **Timing-sensitive tests are flaky in shared environments.** A single busy CI neighbour
  can shift an `elements_per_second` measurement enough to look like a regression.

If a consistent reference baseline is needed, consider a manually-triggered
`workflow_dispatch` GitHub Actions job pinned to a self-hosted or dedicated large runner,
with results committed to a `benchmarks/results/` directory.

---

## How to run

```bash
# Run a single queue type and start method (quick sanity check)
cd benchmarks
python -m pytest throughput_test_exclude.py -k "queue_Queue_and_fork_and_index_1" --no-header -v

# Run the full suite (slow — all queue types, all start methods, 5 rounds)
python -m pytest throughput_test_exclude.py --no-header -v

# Print the latest results from the database
python throughput_results.py
```

Results are stored in `benchmarks/throughput/throughput.sqlite.db` (created automatically
on first run). The file is listed in `.gitignore` — results are not committed to the repo.

---

## How to interpret results

The benchmark captures three metrics per `(queue_type, start_method)` combination:

| Metric | What it measures | What affects it most |
|--------|-----------------|----------------------|
| `time_to_first_element` | Startup latency: process/thread creation + first message delivery | `start_method` (spawn > forkserver > fork); queue type |
| `avg_time_per_element` | Steady-state per-message latency after warmup | Queue type; OS scheduling |
| `elements_per_second` | Sustained throughput, reported as actual vs. baseline ratio | CPU speed; queue contention; `start_method` |

### The baseline ratio

The `elements_per_second_queuelink_baseline` metric measures direct queue put/get speed
on the same machine without any QueueLink in the path. The `_actual` result adds the
QueueLink publisher in the middle. The ratio `actual / baseline` is the most meaningful
number to compare across machines — it normalises out raw CPU speed and measures the
overhead introduced by QueueLink itself.

- **Ratio close to 1.0**: QueueLink adds negligible overhead. The bottleneck is the
  underlying queue implementation.
- **Ratio significantly below 1.0**: The publisher loop or the extra queue hop is a
  bottleneck. Worth investigating if this appears after a code change.

### Handle adapter metrics

For `QueueHandleAdapterReader`:

| Metric | Description |
|--------|-------------|
| `reader_time_to_first_line` | Seconds from adapter start until the first line appears in the queue |
| `reader_lines_per_second` | Sustained line throughput from subprocess stdout through the adapter |

For `QueueHandleAdapterWriter`:

| Metric | Description |
|--------|-------------|
| `writer_lines_per_second` | Sustained line throughput from queue through the adapter to a temp file |

---

## How host context is recorded

Each benchmark session writes a `host_info` row to the SQLite database. This records the
machine that produced the results so they remain interpretable when comparing across
environments.

| Column | Source |
|--------|--------|
| `hostname` | `platform.node()` |
| `cpu_model` | `platform.processor()` (may be empty on some platforms) |
| `cpu_count` | `os.cpu_count()` |
| `python_version` | `sys.version` |
| `os_platform` | `platform.platform()` |

To join results with host context:

```sql
SELECT h.hostname, h.cpu_model, h.cpu_count, h.os_platform,
       r.test_name, r.start_method, r.source, r.destination,
       AVG(CAST(r.result AS REAL)) as avg_result, r.result_unit
FROM results r
JOIN host_info h ON r.session_id = h.session_id
WHERE r.session_id = '<session_id>'
GROUP BY r.test_name, r.start_method, r.source, r.destination, r.result_unit
ORDER BY r.test_name, r.start_method;
```

Note: The `host_info` table captures static machine properties, not real-time load or
memory pressure at run time. For the most reproducible results, run benchmarks on an
otherwise-idle machine. If real-time resource data is needed, `psutil` (not a current
dependency) can provide it, but adds noise to results rather than explaining them.

---

## Best practices for reproducible results

- **Run on an idle machine.** Close browser tabs, compilation jobs, and other CPU-intensive
  tasks before running. Even background processes can shift `elements_per_second`
  measurements by 10–20%.
- **Use a consistent Python version.** Results vary across CPython releases — always record
  the `python_version` column when comparing sessions.
- **Use the 5-round default.** Each parameterised test is run 5 times (the `index`
  parameter). Average over all 5 rounds for the most stable estimate.
- **Expect `spawn` and `forkserver` to be slower on `time_to_first_element`.** Process
  startup cost is real and expected — it is not a bug in the library.
- **Use the baseline ratio, not raw numbers.** Raw `elements_per_second` depends on CPU
  speed; the `actual / baseline` ratio does not.
