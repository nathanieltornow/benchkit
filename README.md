# benchkit

`benchkit` is a small Python library for benchmark sweeps with durable per-run artifacts and a simple analysis API.

## Core API

- `@bk.func("...")` decorates a benchmark function.
- Calling the decorated function runs one case and returns a read-only `Run`.
- `.sweep(cases=[...])` runs many cases in the current sweep and skips cases that already completed successfully.
- `bk.open_analysis("...")` reopens the current sweep for analysis and plotting.
- `bk.context()` exposes the active run context for saving artifacts and metrics.
- `bk.run(...)` executes an external command and captures stdout, stderr, and command metadata as artifacts.

## Install

```bash
uv sync
```

Or install it into another project:

```bash
uv add /path/to/benchkit
```

## Benchmark File Contract

Benchmark files should export:

- one decorated benchmark function, usually as `BENCH`
- `CASES`, a list of explicit case objects or dicts

The CLI uses that contract.

## End-to-End Example

```python
from __future__ import annotations

import json
import matplotlib.pyplot as plt

import benchkit as bk


@bk.func("routing-quality")
def routing_quality(circuit: str, backend: str) -> None:
    bk.context().save_json("case.json", {"circuit": circuit, "backend": backend})
    result = bk.run(
        [
            "python3",
            "-c",
            (
                "import json; "
                "print(json.dumps({"
                "'compile_time_ms': 12.5,"
                "'swap_count': 7,"
                "'estimated_fidelity': 0.93"
                "}))"
            ),
        ],
        name="compiler",
    )
    payload = json.loads(result.stdout)
    bk.context().save_result(
        {
            "compile_time_ms": float(payload["compile_time_ms"]),
            "swap_count": int(payload["swap_count"]),
            "estimated_fidelity": float(payload["estimated_fidelity"]),
        }
    )


BENCH = routing_quality
CASES = [
    {"circuit": "ghz_16", "backend": "cpu"},
    {"circuit": "ghz_16", "backend": "gpu"},
    {"circuit": "qaoa_20", "backend": "cpu"},
    {"circuit": "qaoa_20", "backend": "gpu"},
]


analysis = routing_quality.sweep(cases=CASES, timeout_seconds=60, max_workers=2)
df = analysis.load_frame()
analysis.save_dataframe(df, "raw-results", file_format="csv")

run = analysis.get_run(
    config={"circuit": "ghz_16", "backend": "cpu"}, rep=1, status="ok"
)
stdout = run.read_text("compiler.stdout.txt")

with bk.pplot():
    FIGURE_WIDTH_MM = 180.0
    FIGURE_HEIGHT_MM = 45.0
    THEME = {
        "cpu": {"color": "#4477AA", "marker": "o", "linestyle": "-", "hatch": None},
        "gpu": {"color": "#EE6677", "marker": "s", "linestyle": "--", "hatch": "//"},
    }

    fig, ax = plt.subplots(figsize=(FIGURE_WIDTH_MM / 25.4, FIGURE_HEIGHT_MM / 25.4))
    summary = df.groupby("config.backend", as_index=False)[
        ["result.compile_time_ms"]
    ].mean()
    for _, row in summary.iterrows():
        style = THEME[row["config.backend"]]
        ax.bar(
            row["config.backend"],
            row["result.compile_time_ms"],
            color=style["color"],
            edgecolor="black",
            hatch=style["hatch"],
        )

analysis.save_figure(fig, plot_name="routing-quality-runtime")
```

For a single case:

```python
run = routing_quality(circuit="ghz_16", backend="cpu")
print(run.metrics)
```

For later analysis:

```python
analysis = bk.open_analysis("routing-quality")
df = analysis.load_frame()
for run in analysis.load_runs(status="ok"):
    print(run.config, run.metrics)
```

## CLI

Run the current sweep:

```bash
benchkit run benchmarks/routing_quality.py
```

Start a fresh sweep:

```bash
benchkit run benchmarks/routing_quality.py --new-sweep
```

List sweeps:

```bash
benchkit sweeps
benchkit sweeps routing-quality
```

List runs:

```bash
benchkit runs routing-quality
benchkit runs routing-quality --sweep 20260320T153015123456Z
benchkit runs routing-quality --status ok
```

## Storage Layout

By default, BenchKit writes to the project-local `.benchkit/` directory rooted at the nearest parent containing `pyproject.toml`, `.git`, or `setup.py`.

```text
.benchkit/
  benchmarks.sqlite
  executions.jsonl
  runs/<benchmark-id>/<sweep-id>/log.jsonl
  runs/<benchmark-id>/<sweep-id>/<run-id>/
  analysis/<benchmark-id>--<sweep-id>/
```

Set `BENCHKIT_HOME=/path/to/output-root` to override that location.

## Conventions

- Use explicit `cases=[...]` as the main sweep API. `bk.grid(...)` is only a convenience for simple Cartesian products.
- Inside the benchmark function, call `bk.context().save_result({...})` once for the canonical final metric row.
- Use `bk.context().append_result({...})` for repeated internal samples.
- Save anything needed later that is not a primary metric as an artifact.
- Prefer `bk.run(...)` for external commands.
- `bk.open_analysis("benchmark-id")` opens the current sweep by default.
- Use `max_workers=1` for timing-sensitive benchmarks unless parallelism is clearly safe.
- Plot scripts should use `180 mm` width for double-column figures and `80 mm` for single-column figures, with a slim height chosen explicitly.
- Every plotting script should define an explicit theme mapping for colors, markers, line styles, and hatches when relevant.
