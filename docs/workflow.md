# Benchmark Workflow

This is the intended workflow for agent-driven benchmark work.

## Core Model

- `BenchFunction`: a decorated benchmark function created with `@bk.func("benchmark-id")`
- `Run`: a read-only stored run with metrics and artifact access
- `Analysis`: a read-only handle for reopening one stored sweep

## Execution Rules

- Write benchmarks as normal Python functions.
- The benchmark function can call any external tool, binary, or script via `bk.run(...)`.
- Save the canonical final metric row with `bk.context().save_result({...})`.
- Use `bk.context().append_result({...})` when one benchmark invocation records multiple internal samples.
- Save all non-metric evidence as artifacts with `save_json`, `save_text`, `save_pickle`, `copy_file`, or `bk.run(...)`.
- Use explicit `cases=[...]` as the main sweep API.
- `bk.grid(...)` is only for simple Cartesian products.
- Sweeps are the only lineage mechanism.
- Resume is always on within the current sweep.
- Start a fresh sweep explicitly when you want a new benchmark campaign.
- Only the project BenchKit root is configurable. Internal paths are library-owned.
- All run metadata is stored in a single SQLite table (`benchmarks.sqlite`). Artifact files live in run directories.
- Use `timeout=` on `bk.run(...)` for long-running external processes.

## Analysis Rules

- Reopen stored runs with `bk.open_analysis("benchmark-id")`.
- Pass `sweep=...` only when you want a non-current stored sweep.
- Use `analysis.load_frame()` for dataframe-based analysis.
- Use `analysis.load_runs()` or `analysis.get_run(...)` when you need artifacts.
- Save derived tables under `analysis.paths.root / "data"/`.
- Save figures with `analysis.save_figure(...)`.
- Reports are agent-managed Markdown files under `analysis.paths.root / "reports"/`.
- Every report must include a rerun command or short rerun procedure.
- Use simple output names like `"raw-results"` or `"main-figure"`, not custom filesystem paths.

## Plot Rules

- Use `with bk.pplot():` for shared style only.
- Plot construction should stay in normal matplotlib, pandas, or seaborn code.
- Use `FIGURE_WIDTH_MM = 180.0` for double-column paper figures.
- Use `FIGURE_WIDTH_MM = 80.0` for single-column paper figures.
- Choose a slim `FIGURE_HEIGHT_MM` explicitly based on context.
- The house default for slim double-column figures is `45.0 mm`.
- For bar plots, use patches with visible outlines.
- For slim figures, sparse hatches like `/` can disappear, especially in legends. Prefer denser variants like `//` or `///` when needed.
- Every plotting script should define an explicit theme mapping.
- A theme should fix color, marker, line style, and hatch choices for recurring labels.

## Project Layout

```text
benchmarks/
  compile_perf.py
plots/
  compile_perf/
    main_figure.py
    appendix_ablation.py
themes/
  compile_perf.py
  shared.py
```

## Example Pattern

```python
import benchkit as bk


@bk.func("compile-perf")
def compile_perf(compiler: str, opt_level: str, source: str) -> None:
    bk.context().save_json("input.json", {"compiler": compiler, "opt_level": opt_level})
    result = bk.run(
        [compiler, f"-{opt_level}", source, "-o", "/dev/null"],
        name="compile",
        timeout=120,
    )
    bk.context().append_result({"phase": "compile", "returncode": result.returncode})
    bk.context().save_result(
        {
            "compile_time_ms": 12.5,
            "binary_size_kb": 340,
        }
    )


CASES = [
    {"compiler": "gcc", "opt_level": "O0", "source": "bench.c"},
    {"compiler": "clang", "opt_level": "O3", "source": "bench.c"},
]


analysis = compile_perf.sweep(cases=CASES)
df = analysis.load_frame()
analysis.save_dataframe(df, "raw-results", file_format="csv")
run = analysis.get_run(
    config={"compiler": "gcc", "opt_level": "O0", "source": "bench.c"},
    status=bk.RunStatus.OK,
)
metadata = run.load_json("compile.run.json")
```

Typical CLI flow:

```bash
benchkit sweeps compile-perf
benchkit runs compile-perf --status ok
```
