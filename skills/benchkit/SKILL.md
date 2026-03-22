---
name: benchkit
description: Design, execute, analyze, and plot reproducible benchmark experiments using the benchkit Python library. Use when the user asks to run experiments, benchmark tools, compare configurations, measure performance, or produce publication-quality plots. Works with any workload -- compiled binaries, scripts, simulations, solvers, or Python functions.
---

# BenchKit

Python library for reproducible benchmark experiments. Orchestration is Python; the workload is anything (Rust, C++, shell scripts, Python).

**Install:** `uv add git+https://github.com/nathanieltornow/benchkit@v0.0.1`

## Project Layout

```
my-project/
  src/
  benchmarks/                   # committed to git
    compile_perf.py
    JOURNAL.md                  # append-only experiment log
  .benchkit/                    # gitignored (DB + artifacts)
```

## API

```python
import benchkit as bk


@bk.func("compile-perf")
def compile_perf(compiler: str, opt_level: str) -> None:
    """Benchmark compile time with 5 reps after warmup."""
    bk.run(
        [compiler, f"-{opt_level}", "bench.c", "-o", "/dev/null"],
        name="warmup",
        timeout=120,
    )
    for i in range(5):
        result = bk.run(
            [compiler, f"-{opt_level}", "bench.c", "-o", "/dev/null"],
            name=f"rep-{i}",
            timeout=120,
        )
        bk.context().save_result({"time_ms": parse_time(result.stdout)})


CASES = bk.grid(compiler=["gcc", "clang"], opt_level=["O0", "O2", "O3"])

if __name__ == "__main__":
    analysis = compile_perf.sweep(cases=CASES, max_workers=4, timeout=300)

    df = analysis.load_frame()
    summary = df.groupby(["config.compiler", "config.opt_level"])["result.time_ms"].agg(
        ["mean", "std"]
    )

    with bk.pplot(preset="double-column", latex=True):
        fig, ax = plt.subplots()
        ...
    analysis.save_figure(fig, plot_name="compile-times")
```

## Rules

### Execution

- `bk.run(command, name=..., timeout=...)` runs any executable and captures stdout/stderr as artifacts.
- `bk.context().save_result({...})` writes one row to the DB. Call it once per repetition.
- Each `.sweep()` call starts a fresh sweep. To resume a crashed sweep, pass `sweep=<id>` explicitly.
- `max_workers=N` for parallel execution (ProcessPoolExecutor). `timeout=` limits each case in seconds.
- Always put `.sweep()` and analysis inside `if __name__ == "__main__":` (required for multiprocessing).
- `bk.grid(...)` for simple Cartesian products. Explicit case lists otherwise.

### Repetitions

Each `save_result()` call writes a separate DB row. Aggregate in pandas:

```python
df = analysis.load_frame()  # all rows, including all reps
summary = df.groupby("config.compiler")["result.time_ms"].agg(["mean", "std"])
```

### Analysis

- `analysis.load_frame()` -- all results as a DataFrame with `config.*` and `result.*` columns.
- `analysis.load_runs()` / `analysis.get_run(config={...})` -- access artifacts.
- `analysis.summary()` -- `{"ok": 50, "failure": 2}`.
- `analysis.is_complete(n)` -- True if n cases succeeded.
- `analysis.save_dataframe(df, "name")` -- save derived tables as CSV.
- `analysis.save_figure(fig, plot_name="name")` -- save PDF + PNG.

### Plotting

- `with bk.pplot(preset="double-column", latex=True):` for paper figures.
- Presets: `double-column` (180x45mm), `single-column` (85x55mm), `slide` (254x143mm).
- Define an explicit theme mapping per figure. Use the Tol colorblind-safe palette.

### Scripts

Every benchmark script must be self-documenting:

1. Module docstring explaining what and why.
2. Cases with comments explaining parameter choices.
3. Benchmark function with docstring.
4. `if __name__ == "__main__":` block.
5. Rerun command at the bottom: `# Rerun: uv run python benchmarks/compile_perf.py`

### Resume

Resume is ONLY for crashes or interruptions. Pass the sweep id explicitly:

```python
analysis = my_benchmark.sweep(cases=CASES, sweep="20260322T143000000000Z")
```

Never resume with changed code. Changed code = fresh sweep (the default).

## Journal -- MANDATORY

**Every experiment gets a journal entry. No exceptions. No deferring.**

After every sweep -- successful, partial, or failed -- append an entry to `benchmarks/JOURNAL.md` before reporting to the user. Create with `# Experiment Journal` header on first use.

```markdown
## compile-perf -- GCC vs Clang optimization levels

**Date:** 2026-03-22
**Sweep:** 20260322T143000000000Z
**Status:** completed

**Goal:** Compare compile times of gcc and clang across O0-O3.
**Cases:** 2 compilers x 3 opt levels x 5 reps = 30 rows.
**Key results:**

- clang O3 is 2.1x faster than gcc O3 (mean 12ms vs 25ms)

**Rerun:** `uv run python benchmarks/compile_perf.py`
```

Rules:

- Always append, never delete. Failed experiments get an entry too.
- Write after the sweep completes, not before. Include actual results.
- One sentence per finding. Link to figures, don't inline tables.

## Workflow

**Do not skip any step.**

1. **Clarify** -- what is being measured and why. No experiments without clear intent.
2. **Implement** -- self-documenting benchmark script in `benchmarks/`.
3. **Execute** -- `.sweep(cases=...)`. Check `analysis.summary()`.
4. **Analyze** -- `load_frame()`, compute summaries.
5. **Plot** -- publication-quality figures.
6. **Journal** -- append entry to `benchmarks/JOURNAL.md`. **Not optional.**
