# benchkit

`benchkit` is a small Python library for running parameter sweeps, logging benchmark results to JSONL, storing artifacts, and saving comparison plots.

## What it provides

- `@benchkit.foreach(...)` for simple benchmark grids
- `benchkit.Sweep(...)` for explicit repeated benchmark sweeps with retries, timeout handling, and optional process parallelism
- `@benchkit.log(...)` for structured JSONL result logging
- `benchkit.load_log(...)` and `benchkit.join_logs(...)` for analysis with pandas
- `@benchkit.timeout(...)`, `@benchkit.retry(...)`, and `@benchkit.catch_failures(...)` for robust benchmark runs
- `benchkit.artifact(...)` for binary outputs such as models, traces, or raw reports
- `benchkit.pplot(...)` for plot defaults and `benchkit.save_figure(...)` for saving figures
- `@benchkit.cache(...)` for local SQLite-backed memoization

By default, outputs go under `.benchkit/`:

- `.benchkit/logs/`
- `.benchkit/artifacts/`
- `.benchkit/cache/`
- `.benchkit/plots/`

Set `BENCHKIT_HOME=/path/to/output-root` to override that location.

## Install

```bash
uv sync
```

Or install it as a package in another project:

```bash
uv add /path/to/benchkit
```

## Quick example

```python
from __future__ import annotations

import matplotlib.pyplot as plt

import benchkit as bk


def benchmark(size: int, backend: str) -> dict[str, float]:
    runtime_ms = size / (4 if backend == "gpu" else 2)
    throughput = size / runtime_ms
    bk.context().save_json(
        "summary.json",
        {"size": size, "backend": backend, "runtime_ms": runtime_ms},
    )
    bk.context().save_pickle("summary.pkl", {"runtime_ms": runtime_ms})
    return {"runtime_ms": runtime_ms, "throughput": throughput}

sweep = bk.Sweep(
    id="matrix",
    fn=benchmark,
    params={"size": [128, 256, 512], "backend": ["cpu", "gpu"]},
    repeat=5,
    retries=2,
    timeout_seconds=30,
    continue_on_failure=True,
    default_result={"runtime_ms": float("inf"), "throughput": 0.0},
    max_workers=1,
)
sweep.run()
df = bk.load_log("matrix.jsonl")
summary = bk.get_artifact(
    "matrix",
    config={"size": 128, "backend": "cpu"},
    rep=1,
    name="summary.pkl",
)
payload = bk.load_pickle(summary)

with bk.pplot():
    fig, ax = plt.subplots()
    bk.bar_comparison(
        ax,
        df,
        keys=["result.runtime_ms", "result.throughput"],
        group_key="config.size",
        error=None,
    )
    ax.legend()

bk.save_figure(fig, plot_name="matrix-summary")
```

## Data model

Each log row contains:

- `config`: bound function arguments, excluding `self` and `cls`
- `result`: the returned value
- `id`: short run id
- `func_name`
- `init_time`
- `timestamp`
- `host`
- `git_commit`
- `git_dirty`
- `benchmark`
- `sweep_id`
- `rep`
- `rep_count`
- `status`
- `attempt`
- `execution_mode`
- `max_workers`
- `error_type` and `error_message` for failed or timed-out cases

`load_log(..., normalize=True)` flattens nested fields into columns such as `config.size` and `result.runtime_ms`.
`list_artifacts(...)` and `get_artifact(...)` query the SQLite artifact index directly.

## Typical workflow

1. Write a benchmark function that returns a JSON-serializable result dict.
   If you need per-run files, call `bk.context()` inside the function and save artifacts through it.
2. Run it with `Sweep(id=..., fn=..., repeat=5)`.
3. Load the JSONL log with `load_log`.
4. Fetch recorded artifacts with `get_artifact(...)` or `list_artifacts(...)` when needed.
5. Use pandas directly or pass the dataframe to plotting helpers.
6. Build figures inside `pplot` and write them with `save_figure`.

## Notes

- `Sweep` runs the Cartesian product of `params` and repeats each case `repeat` times.
- `Sweep` can retry failed cases and convert failures/timeouts into a default result when `continue_on_failure=True`.
- `Sweep(max_workers>1)` uses process-based parallel execution while keeping log writing in the parent process.
- For publishable runtime measurements, prefer `max_workers=1` to avoid cross-case resource contention.
- `Sweep(id="matrix", ...)` defaults to `.benchkit/logs/matrix.jsonl` and `.benchkit/state/matrix.sqlite`.
- `Sweep(resume=True)` skips previously successful `(benchmark, config, rep)` cases for that sweep id and log path.
- If the sweep function calls `bk.context()`, artifacts are stored under `.benchkit/artifacts/<id>/<case-key>/rep-<n>/`.
- BenchKit also indexes artifacts in `.benchkit/state/artifacts.sqlite`.
- Use `get_artifact("matrix", config={...}, rep=1, name="summary.pkl")` to fetch one artifact directly.
- Use `list_artifacts("matrix", config={...})` to inspect all indexed artifacts for one input.
- Use `load_pickle(...)` for artifacts stored with `save_pickle(...)`.
- Use `clear_sweep_artifacts("matrix")` to remove all stored artifacts for a sweep id.
- If you use `timeout_seconds` in a script entrypoint, guard execution with `if __name__ == "__main__":`.
- `foreach` still works for small decorator-based experiments.
- Relative log paths resolve to JSONL files under `.benchkit/logs/`.
- `pplot` applies portable matplotlib defaults.
- `save_figure` writes timestamped output files.
- `cache` is useful for deterministic preprocessing steps around expensive benchmarks.

See [examples/simple.py](/Users/nathanieltornow/code/benchkit/examples/simple.py) for a runnable example.
