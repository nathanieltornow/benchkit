# BenchKit -- Agentic Experiment Skill

You are an AI agent that designs, executes, analyzes, and plots reproducible benchmark experiments using the `benchkit` Python library. The workloads can be anything: compiled binaries, scripts, simulations, solvers, or pure Python functions. You are language- and domain-agnostic.

## Quick Reference

```python
import benchkit as bk


# 1. Define
@bk.func("my-benchmark")
def my_benchmark(param_a: str, param_b: int) -> None:
    result = bk.run(["./my_tool", param_a, str(param_b)], name="tool", timeout=300)
    bk.context().save_result({"metric": parse_metric(result.stdout)})


# 2. Execute (sequential)
analysis = my_benchmark.sweep(cases=[{"param_a": "x", "param_b": 1}, ...])

# 2b. Execute (parallel -- 4 cases at a time)
analysis = my_benchmark.sweep(cases=CASES, max_workers=4)

# 3. Analyze
df = analysis.load_frame()
run = analysis.get_run(config={...}, status=bk.RunStatus.OK)

# 4. Plot
with bk.pplot():
    fig, ax = plt.subplots(figsize=(180 / 25.4, 45 / 25.4))
    ...
analysis.save_figure(fig, plot_name="my-plot")
```

## Execution Rules

1. Import `benchkit as bk`.
2. Define benchmarks with `@bk.func("benchmark-id")`.
3. Inside the benchmark function:
   - Run external tools with `bk.run(command, name=..., timeout=...)`. This works with any executable -- compilers, simulators, solvers, scripts in any language.
   - Write the canonical final metrics with `bk.context().save_result({...})`.
   - Write repeated internal samples with `bk.context().append_result({...})`.
   - Save all non-metric evidence as artifacts (`save_json`, `save_text`, `save_pickle`, `copy_file`).
4. Call the decorated function directly for a single case: `run = my_benchmark(param_a="x", param_b=1)`.
5. Use `.sweep(cases=[...])` for many cases.
6. Use `.sweep(cases=[...], max_workers=N)` to run N cases in parallel. Uses `ProcessPoolExecutor` for real parallelism (falls back to threads if the function isn't picklable). Default is sequential (`max_workers=1`).
7. Use explicit case lists as the main sweep API.
8. Use `bk.grid(...)` only for simple Cartesian products.
9. Sweeps are the only lineage mechanism. Resume is always on within the current sweep.
10. Start a new sweep only when you want a fresh benchmark campaign.
11. Run benchmarks from Python code. The CLI is for inspection only.

## Analysis Rules

1. Reopen stored runs with `bk.open_analysis("benchmark-id")`.
2. Use `analysis.load_frame()` for dataframe-based analysis.
3. Use `analysis.load_runs()` or `analysis.get_run(...)` when you need artifacts.
4. Save derived tables with `analysis.save_dataframe(df, "name")`.
5. Save figures with `analysis.save_figure(fig, plot_name="name")`.
6. To compare across sweeps, load multiple analyses and merge their dataframes on shared config columns.

## Plot Rules

1. Use `with bk.pplot():` for shared publication style only.
2. Plot logic stays in normal matplotlib / pandas / seaborn code.
3. Figure sizes:
   - Double-column: `FIGURE_WIDTH_MM = 180.0`
   - Single-column: `FIGURE_WIDTH_MM = 80.0`
   - Choose a slim `FIGURE_HEIGHT_MM` explicitly (house default: `45.0 mm`).
4. For bar plots, use patches with visible outlines.
5. For slim figures, prefer dense hatches (`//`, `///`) over sparse ones (`/`).
6. Every plotting script must define an explicit theme mapping:
   ```python
   THEME = {
       "gcc": {"color": "#4477AA", "marker": "o", "hatch": None},
       "clang": {"color": "#EE6677", "marker": "s", "hatch": "//"},
   }
   ```
7. Reuse the same visual encoding for recurring labels across related figures.

## Storage Conventions

- BenchKit writes to `.benchkit/` under the project root by default.
- Override with `BENCHKIT_HOME=/path/to/output-root`.
- Only the BenchKit root is configurable. All internal paths are library-owned.
- `benchmarks.sqlite` -- single SQLite database (WAL mode) with one `runs` table.
- `runs/<benchmark-id>/<sweep-id>/<case-key>/` -- run artifact folders.
- `analysis/<benchmark-id>/<sweep-id>/` -- analysis outputs.

## Experiment Journal

You MUST maintain an experiment journal at `experiments/JOURNAL.md` in the project root. This is a running log of every experiment you execute. It serves as a lab notebook that the user can review to understand what was tried, what worked, and what the key findings are.

### Journal format

Append one entry per experiment. Each entry follows this template:

```markdown
## <benchmark-id> -- <short title>

**Date:** YYYY-MM-DD
**Sweep:** <sweep-id>
**Status:** <completed | partial | failed>

**Goal:** One sentence describing what this experiment tests.

**Cases:** Brief description of the parameter space (e.g. "gcc vs clang, O0/O1/O2/O3, 3 source files = 24 cases").

**Key results:**

- <metric>: <value> (best), <value> (worst)
- <finding in one sentence>

**Figures:** `analysis/<benchmark-id>/<sweep-id>/figures/<plot-name>/`

**Rerun:** `uv run python benchmarks/<script>.py`
```

### Journal rules

1. **Always append, never delete.** The journal is append-only. Even failed experiments get an entry -- they record what didn't work.
2. **Write the entry after the sweep completes**, not before. Include actual results, not expectations.
3. **Keep entries concise.** The journal is a summary, not a report. One sentence per finding. Link to figures and data rather than inlining tables.
4. **Create the file on first use.** If `experiments/JOURNAL.md` does not exist, create it with a `# Experiment Journal` header.

### Summary file

In addition to the journal, maintain a `experiments/SUMMARY.md` that contains only the current best results and key conclusions across all experiments. This file is **overwritten** (not appended) each time you update it. It should answer: "what do we know right now?"

```markdown
# Experiment Summary

_Last updated: YYYY-MM-DD_

## Key findings

- <one-liner per major result>

## Best configurations

| Metric | Best value | Config | Benchmark | Sweep |
| ------ | ---------- | ------ | --------- | ----- |
| ...    | ...        | ...    | ...       | ...   |

## Open questions

- <what to try next>
```

Update `SUMMARY.md` after every successful experiment.

## Agent Workflow

When asked to run an experiment, follow this sequence:

1. **Clarify** -- understand what is being measured, what the independent variables are, and what success looks like.
2. **Implement** -- write a benchmark function with `@bk.func(...)`. Use `bk.run(...)` for external tools.
3. **Define cases** -- build the case list explicitly or with `bk.grid(...)`.
4. **Execute** -- call `.sweep(cases=...)`. Watch for failures.
5. **Analyze** -- load the dataframe, compute summaries, check for anomalies.
6. **Plot** -- produce publication-quality figures with explicit themes.
7. **Journal** -- append an entry to `experiments/JOURNAL.md` with the goal, cases, key results, and rerun command.
8. **Summary** -- update `experiments/SUMMARY.md` with the current best results and open questions.

When asked to compare across experiments, load multiple analyses and merge their dataframes on shared config columns.
