# benchkit

`benchkit` is a small Python library for running parameter sweeps, logging benchmark results, storing artifacts, and saving comparison plots.

## What it provides

- `@benchkit.foreach(...)` for simple benchmark grids
- `@benchkit.log(...)` for structured JSONL result logging
- `benchkit.load_log(...)` and `benchkit.join_logs(...)` for analysis with pandas
- `@benchkit.timeout(...)`, `@benchkit.retry(...)`, and `@benchkit.catch_failures(...)` for robust benchmark runs
- `benchkit.artifact(...)` for binary outputs such as models, traces, or raw reports
- `@benchkit.pplot(...)` plus plotting helpers for saving figures consistently
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


@bk.foreach(size=[128, 256, 512])
@bk.foreach(backend=["cpu", "gpu"])
@bk.log("matrix.jsonl")
def benchmark(size: int, backend: str) -> dict[str, float]:
    runtime_ms = size / (4 if backend == "gpu" else 2)
    throughput = size / runtime_ms
    return {"runtime_ms": runtime_ms, "throughput": throughput}


benchmark()
df = bk.load_log("matrix.jsonl")

fig, ax = plt.subplots()
bk.bar_comparison(
    ax,
    df,
    keys=["result.runtime_ms", "result.throughput"],
    group_key="config.size",
    error=None,
)
ax.legend()

bk.pplot(plot_name="matrix-summary")(lambda: fig)()
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

`load_log(..., normalize=True)` flattens nested fields into columns such as `config.size` and `result.runtime_ms`.

## Typical workflow

1. Decorate a benchmark function with `foreach`, `log`, and optional reliability decorators.
2. Execute the function once to run the sweep.
3. Load the JSONL log with `load_log`.
4. Use pandas directly or pass the dataframe to plotting helpers.
5. Save figures with `pplot`.

## Notes

- `foreach` zips iterables at each decorator level. Stacking decorators creates Cartesian products.
- `pplot` uses portable matplotlib defaults and writes timestamped files.
- `cache` is useful for deterministic preprocessing steps around expensive benchmarks.

See [examples/simple.py](/Users/nathanieltornow/code/benchkit/examples/simple.py) for a runnable example.
