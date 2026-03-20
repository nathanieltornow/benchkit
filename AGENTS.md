# Agent Notes

Use `benchkit` as a local library for benchmark execution, artifact capture, and later analysis.

## Preferred API

1. Import `benchkit as bk`.
2. Define benchmarks with `@bk.func("benchmark-id")`.
3. Inside the benchmark function:
   - write the canonical final metrics with `bk.context().save_result({...})`
   - write repeated internal samples with `bk.context().append_result({...})`
   - save all non-metric evidence as artifacts
4. Call the decorated function directly for a single case.
5. Use `.sweep(cases=...)` for many cases.
6. Reopen stored runs with `bk.open_analysis("benchmark-id")`.

## Benchmark Rules

- Use explicit case lists as the main sweep API.
- Use `bk.grid(...)` only for simple Cartesian products.
- Sweeps are the only lineage mechanism.
- Resume is always on within the current sweep.
- Start a new sweep only when you want a fresh benchmark campaign.
- If a benchmark calls external tools, prefer `bk.run(...)`.
- If something matters later and it is not a logged metric, save it as an artifact.

## Analysis Rules

- Use `analysis.load_frame()` for dataframe-based analysis.
- Use `analysis.load_runs()` or `analysis.get_run(...)` when you need artifacts.
- Save derived tables under `analysis.paths.root / "data"/`.
- Save figures with `analysis.save_figure(...)`.
- Reports are agent-managed Markdown files under `analysis.paths.root / "reports"/`.
- Every report must include a rerun command or short rerun procedure.

## Plot Rules

- Use `with bk.pplot():` for shared style only.
- Plot logic should stay in normal matplotlib, pandas, or seaborn code.
- Use `FIGURE_WIDTH_MM = 180.0` for double-column figures.
- Use `FIGURE_WIDTH_MM = 80.0` for single-column figures.
- Choose a slim `FIGURE_HEIGHT_MM` explicitly.
- The house default for slim double-column figures is `45.0 mm`.
- For bar plots, use patches with visible outlines.
- For slim figures, avoid sparse hatches like `/` when they need to stay visible. Prefer `//` or `///`.
- Every plotting script should define an explicit theme mapping.
- Reuse the same visual encoding for recurring labels across related figures.

## Storage Conventions

- BenchKit writes to the project-local `.benchkit/` directory by default.
- The global project registry is `.benchkit/benchmarks.sqlite`.
- The execution event log is `.benchkit/executions.jsonl`.
- Run folders live under `.benchkit/runs/<benchmark-id>/<sweep-id>/<run-id>/`.
- Analysis outputs live under `.benchkit/analysis/<benchmark-id>--<sweep-id>/`.
