# benchkit

`benchkit` is a small Python library for running benchmark sweeps, capturing artifacts, and analyzing results. It works with any workload -- Python functions, compiled binaries, shell scripts, or external tools in any language.

## Core API

- `@bk.func("...")` decorates a benchmark function.
- Calling the decorated function runs one case and returns a read-only `Run`.
- `.sweep(cases=[...])` runs many cases in the current sweep, skipping cases that already completed. Pass `max_workers=N` to run N cases in parallel.
- `bk.open_analysis("...")` reopens a stored sweep for analysis and plotting.
- `bk.context()` exposes the active run context for saving artifacts and metrics.
- `bk.run(...)` executes an external command (any language/binary) and captures stdout, stderr, and metadata as artifacts.

## Install

```bash
uv add git+https://github.com/nathanieltornow/benchkit@v0.0.1
```

## Set Up in a New Project

```bash
# 1. Add benchkit to your project
uv add git+https://github.com/nathanieltornow/benchkit@v0.0.1

# 2. Install the Claude Code skills (experiment + plotting)
benchkit init
```

This creates `.claude/skills/benchkit/` and `.claude/skills/benchkit-plot/` in your project. Claude Code auto-discovers both skills and can use them automatically or via `/benchkit`. Your project's `AGENTS.md` stays untouched.

To install globally (every Claude Code conversation):

```bash
benchkit install-skill
```

The project itself can be in any language.

## End-to-End Example

```python
from __future__ import annotations

import json
import matplotlib.pyplot as plt

import benchkit as bk


@bk.func("compile-benchmark")
def compile_benchmark(compiler: str, opt_level: str, source: str) -> None:
    """Benchmark a compiler on a source file."""
    result = bk.run(
        [compiler, f"-{opt_level}", "-o", "/dev/null", source],
        name="compile",
        timeout=120,
    )
    bk.context().save_result(
        {
            "compile_time_ms": 12.5,  # parse from result.stdout in practice
            "binary_size_kb": 340,
            "returncode": result.returncode,
        }
    )


CASES = [
    {"compiler": "gcc", "opt_level": "O0", "source": "bench.c"},
    {"compiler": "gcc", "opt_level": "O3", "source": "bench.c"},
    {"compiler": "clang", "opt_level": "O0", "source": "bench.c"},
    {"compiler": "clang", "opt_level": "O3", "source": "bench.c"},
]

analysis = compile_benchmark.sweep(cases=CASES)
df = analysis.load_frame()
analysis.save_dataframe(df, "raw-results", file_format="csv")

# Access individual run artifacts
run = analysis.get_run(
    config={"compiler": "gcc", "opt_level": "O0", "source": "bench.c"},
    status=bk.RunStatus.OK,
)
stdout = run.read_text("compile.stdout.txt")

# Plot
with bk.pplot():
    FIGURE_WIDTH_MM = 180.0
    FIGURE_HEIGHT_MM = 45.0
    THEME = {
        "gcc": {"color": "#4477AA", "marker": "o", "hatch": None},
        "clang": {"color": "#EE6677", "marker": "s", "hatch": "//"},
    }

    fig, ax = plt.subplots(figsize=(FIGURE_WIDTH_MM / 25.4, FIGURE_HEIGHT_MM / 25.4))
    summary = df.groupby("config.compiler", as_index=False)[
        ["result.compile_time_ms"]
    ].mean()
    for _, row in summary.iterrows():
        style = THEME[row["config.compiler"]]
        ax.bar(
            row["config.compiler"],
            row["result.compile_time_ms"],
            color=style["color"],
            edgecolor="black",
            hatch=style["hatch"],
        )

analysis.save_figure(fig, plot_name="compile-times")
```

To run cases in parallel (e.g. 4 at a time):

```python
analysis = compile_benchmark.sweep(cases=CASES, max_workers=4)
```

For a single case:

```python
run = compile_benchmark(compiler="gcc", opt_level="O3", source="bench.c")
print(run.metrics)
```

For later analysis:

```python
analysis = bk.open_analysis("compile-benchmark")
df = analysis.load_frame()
for run in analysis.load_runs(status=bk.RunStatus.OK):
    print(run.config, run.metrics)
```

## CLI

The CLI is for inspecting stored sweeps and runs, not for running benchmarks.

```bash
benchkit sweeps
benchkit sweeps compile-benchmark
benchkit runs compile-benchmark
benchkit runs compile-benchmark --sweep 20260320T153015123456Z
benchkit runs compile-benchmark --status ok
```

## Storage Layout

By default, BenchKit writes to `.benchkit/` under the nearest project root (containing `pyproject.toml`, `.git`, or `setup.py`).

```text
.benchkit/
  benchmarks.sqlite          # single table, WAL mode
  runs/<benchmark>/<sweep>/<case>/   # artifact directories
  analysis/<benchmark>/<sweep>/      # analysis outputs
```

All run metadata (config, metrics, status, environment) lives in the SQLite database. Artifact files (stdout, saved JSON/pickle, etc.) live in the run directories.

Set `BENCHKIT_HOME=/path/to/output-root` to override.

## Conventions

- Use explicit `cases=[...]` as the main sweep API. `bk.grid(...)` is only a convenience for simple Cartesian products.
- Inside the benchmark function, call `bk.context().save_result({...})` once for the canonical final metric row.
- Use `bk.context().append_result({...})` for repeated internal samples.
- Save anything needed later that is not a primary metric as an artifact.
- Prefer `bk.run(...)` for external commands -- it works with any executable.
- `bk.open_analysis("benchmark-id")` opens the current sweep by default.
- Run benchmarks from Python, not via the CLI.
- Treat paths below `.benchkit/` as library-owned.
