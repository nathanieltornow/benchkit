---
name: benchkit
description: Design, execute, analyze, and plot reproducible benchmark experiments using the benchkit Python library. Use when the user asks to run experiments, benchmark tools, compare configurations, measure performance, or produce publication-quality plots. Works with any workload -- compiled binaries, scripts, simulations, solvers, or Python functions.
---

# BenchKit -- Agentic Experiment Skill

BenchKit (`benchkit`) is a Python library for running reproducible benchmark experiments, capturing artifacts, and analyzing results. It works with any workload -- Python functions, compiled binaries (Rust, C++, etc.), shell scripts, or external tools in any language. The benchmark orchestration is always Python; the workload is anything.

**Install:** `uv add git+https://github.com/nathanieltornow/benchkit@v0.0.1`

**Source:** https://github.com/nathanieltornow/benchkit

## Project Layout

All benchmark work lives in `benchmarks/` inside the project. This folder is committed to git so experiments are versioned and shared with collaborators. The `.benchkit/` directory (SQLite DB + artifacts) is gitignored -- results are reproduced by re-running scripts.

```
my-project/
  src/                          # project source code
  benchmarks/                   # committed -- all experiment work lives here
    compile_perf.py             # benchmark scripts
    simulation_accuracy.py
    JOURNAL.md                  # append-only experiment log
    SUMMARY.md                  # current best results (overwritten)
  .benchkit/                    # gitignored -- DB + artifacts
  .gitignore                    # must include .benchkit/
```

## Quick Reference

```python
import benchkit as bk


@bk.func("my-benchmark")
def my_benchmark(param_a: str, param_b: int) -> None:
    result = bk.run(["./my_tool", param_a, str(param_b)], name="tool", timeout=300)
    bk.context().save_result({"metric": parse_metric(result.stdout)})


CASES = [{"param_a": "x", "param_b": 1}, {"param_a": "y", "param_b": 2}]

if __name__ == "__main__":
    analysis = my_benchmark.sweep(cases=CASES, max_workers=4, timeout=300)
    df = analysis.load_frame()
    with bk.pplot(preset="double-column", latex=True):
        fig, ax = plt.subplots()
        ...
    analysis.save_figure(fig, plot_name="my-plot")
```

**Important:** Always put `.sweep()`, analysis, and plotting inside `if __name__ == "__main__":`. This is required for `max_workers > 1` because `ProcessPoolExecutor` re-imports the module in child processes.

## Execution Rules

1. Import `benchkit as bk`.
2. Define benchmarks with `@bk.func("benchmark-id")`.
3. Inside the benchmark function:
   - Run external tools with `bk.run(command, name=..., timeout=...)`. This works with any executable -- compilers, simulators, solvers, scripts in any language.
   - Write the canonical final metrics with `bk.context().save_result({...})`.
   - Write repeated internal samples with `bk.context().append_result({...})`.
   - Save all non-metric evidence as artifacts (`save_json`, `save_text`, `save_pickle`, `copy_file`).
4. Call the decorated function directly for a single case: `run = my_benchmark(param_a="x", param_b=1)`.
5. Use `.sweep(cases=[...])` for many cases. **Each `.sweep()` call starts a fresh sweep.**
6. Use `.sweep(cases=[...], max_workers=N)` for parallel execution.
7. Use `timeout=` on `.sweep()` to limit each case (seconds). Timed-out cases are recorded as failures.
8. Use `bk.grid(...)` only for simple Cartesian products.
9. Run benchmarks from Python scripts. The CLI is for inspection only.

### Resume

Resume is ONLY for recovering from crashes, interruptions, or retrying failed cases. It is NOT the default.

To resume, pass the sweep id from the failed run explicitly:

```python
# First run -- crashed after 50 of 100 cases
analysis = my_benchmark.sweep(cases=CASES)
# prints: my-benchmark: 50/100 ... then crashes

# Resume -- pass the sweep id, completed cases are skipped
analysis = my_benchmark.sweep(cases=CASES, sweep="20260322T143000000000Z")
```

Use `analysis.summary()` and `analysis.is_complete(len(CASES))` to check if all cases finished.

**Never resume to re-run with changed code.** If the benchmark function or tooling changed, start a fresh sweep (the default). Stale results from old code are worthless.

## Script Conventions

Every benchmark script MUST be self-documenting. Always write scripts with:

1. **A module docstring** explaining what the experiment measures and why.
2. **Cases defined explicitly** with a comment explaining the parameter choices:
   ```python
   # Compare gcc and clang across optimization levels on the main benchmark source.
   CASES = bk.grid(compiler=["gcc", "clang"], opt_level=["O0", "O1", "O2", "O3"])
   ```
3. **The benchmark function** with a docstring describing what it runs and what metrics it captures.
4. **A `if __name__ == "__main__":` block** for all execution, analysis, and plotting. Required for `max_workers > 1`.
5. **A rerun command** at the bottom: `# Rerun: uv run python benchmarks/compile_perf.py`

## Analysis Rules

1. Reopen stored runs with `bk.open_analysis("benchmark-id")`.
2. Use `analysis.load_frame()` for dataframe-based analysis.
3. Use `analysis.load_runs()` or `analysis.get_run(...)` when you need artifacts.
4. Use `analysis.summary()` to see run counts by status.
5. Use `analysis.is_complete(n)` to check if all n cases succeeded.
6. Save derived tables with `analysis.save_dataframe(df, "name")`.
7. Save figures with `analysis.save_figure(fig, plot_name="name")`.

## Plot Rules

1. Use `with bk.pplot():` for shared publication style only.
2. Plot logic stays in normal matplotlib / pandas / seaborn code.
3. Figure sizes:
   - Double-column: `preset="double-column"` (180 x 45 mm)
   - Single-column: `preset="single-column"` (85 x 55 mm)
   - Slide: `preset="slide"` (254 x 143 mm)
4. Use `latex=True` when the paper uses LaTeX.
5. Every plotting script must define an explicit theme mapping.
6. Reuse the same visual encoding for recurring labels across related figures.

## Documentation -- MANDATORY

**You MUST document every experiment. No exceptions.** After every sweep -- successful, partial, or failed -- you MUST update both the journal and the summary. Do not skip this step. Do not defer it. Do not say "I'll update the journal later." The journal and summary are updated immediately after analyzing results, before reporting back to the user.

### Journal (`benchmarks/JOURNAL.md`)

Append-only log of every experiment. Create with `# Experiment Journal` header on first use.

```markdown
## <benchmark-id> -- <short title>

**Date:** YYYY-MM-DD
**Sweep:** <sweep-id>
**Status:** <completed | partial | failed>

**Goal:** One sentence describing what this experiment tests.

**Cases:** Brief description of the parameter space (e.g. "gcc vs clang, O0-O3, 3 sources = 24 cases").

**Key results:**

- <metric>: <value> (best), <value> (worst)
- <finding in one sentence>

**Figures:** `.benchkit/analysis/<benchmark-id>/<sweep-id>/figures/`

**Rerun:** `uv run python benchmarks/<script>.py`
```

Rules:

- **Always append, never delete.** Failed experiments get an entry too -- they record what didn't work.
- **Write after the sweep completes**, not before. Include actual results.
- **Keep entries concise.** One sentence per finding.

### Summary (`benchmarks/SUMMARY.md`)

Overwritten each time. Answers: "what do we know right now?"

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

## Agent Workflow

When asked to run an experiment, follow this sequence. **Do not skip any step.**

1. **Clarify** -- understand what is being measured, what the independent variables are, and what success looks like. Do not run experiments without clear intent.
2. **Implement** -- write a self-documenting benchmark script in `benchmarks/`.
3. **Execute** -- call `.sweep(cases=...)`. Check `analysis.summary()` for failures.
4. **Analyze** -- load the dataframe, compute summaries, check for anomalies.
5. **Plot** -- produce publication-quality figures with explicit themes.
6. **Journal** -- append an entry to `benchmarks/JOURNAL.md`. **This is not optional.**
7. **Summary** -- update `benchmarks/SUMMARY.md`. **This is not optional.**

Only after completing ALL steps, report results to the user.
