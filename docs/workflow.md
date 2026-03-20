# Benchmark Workflow

This is the intended workflow for agent-driven benchmark work.

## Core Model

- `BenchFunction`: a decorated benchmark function created with `@bk.func("benchmark-id")`
- `Run`: a read-only stored run with metrics and artifact access
- `Analysis`: a read-only handle for reopening one stored sweep

## Execution Rules

- Write benchmarks as normal Python functions.
- Save the canonical final metric row with `bk.context().save_result({...})`.
- Use `bk.context().append_result({...})` when one benchmark invocation records multiple internal samples.
- Save all non-metric evidence as artifacts with `save_json`, `save_text`, `save_pickle`, `copy_file`, or `bk.run(...)`.
- Use explicit `cases=[...]` as the main sweep API.
- `bk.grid(...)` is only for simple Cartesian products.
- Sweeps are the only lineage mechanism.
- Resume is always on within the current sweep.
- Start a fresh sweep explicitly when you want a new benchmark campaign.

## Analysis Rules

- Reopen stored runs with `bk.open_analysis("benchmark-id")`.
- Pass `sweep=...` only when you want a non-current stored sweep.
- Use `analysis.load_frame()` for dataframe-based analysis.
- Use `analysis.load_runs()` or `analysis.get_run(...)` when you need artifacts.
- Save derived tables under `analysis.paths.root / "data"/`.
- Save figures with `analysis.save_figure(...)`.
- Reports are agent-managed Markdown files under `analysis.paths.root / "reports"/`.
- Every report must include a rerun command or short rerun procedure.

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
  routing_quality.py
plots/
  routing_quality/
    main_figure.py
    appendix_ablation.py
themes/
  routing_quality.py
  shared.py
```

Benchmark files should export:

- `BENCH`
- `CASES`

## Example Pattern

```python
import benchkit as bk


@bk.func("routing-quality")
def routing_quality(size: int, backend: str) -> None:
    bk.context().save_json("input.json", {"size": size, "backend": backend})
    result = bk.run(["python3", "-c", "print('ok')"], name="generator")
    bk.context().append_result({"phase": "generator", "returncode": result.returncode})
    bk.context().save_result(
        {
            "compile_time_ms": float(size),
            "estimated_fidelity": 0.9,
        }
    )


BENCH = routing_quality
CASES = [
    {"size": 8, "backend": "heuristic"},
    {"size": 16, "backend": "search"},
]


analysis = routing_quality.sweep(cases=CASES, max_workers=2)
df = analysis.load_frame()
analysis.save_dataframe(df, "raw-results", file_format="csv")
run = analysis.get_run(config={"size": 8, "backend": "heuristic"}, rep=1, status="ok")
trace = run.load_json("generator.run.json")
```

Typical CLI flow:

```bash
benchkit run benchmarks/routing_quality.py
benchkit run benchmarks/routing_quality.py --new-sweep
benchkit sweeps routing-quality
benchkit runs routing-quality --status ok
```
