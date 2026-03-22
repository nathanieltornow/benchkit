---
name: benchkit
description: Design, execute, analyze, and plot reproducible benchmark experiments using the benchkit Python library. Use when the user asks to run experiments, benchmark tools, compare configurations, measure performance, or produce publication-quality plots. Works with any workload -- compiled binaries, scripts, simulations, solvers, or Python functions.
---

# BenchKit

Python library for reproducible benchmark experiments. Orchestration is Python; the workload is anything (Rust, C++, shell scripts, Python).

**Install:** `uv add --group bench git+https://github.com/nathanieltornow/benchkit@v0.0.1`

**Every experiment must be journaled. Journal path: `$BENCHKIT_JOURNAL`.**

## Project Layout

```
my-project/
  src/
  benchmarks/
    scripts/                    # benchmark definitions (persistent, committed)
      compile_perf.py
      decoder_comparison.py
    analysis/                   # analysis + plotting (can be rewritten freely)
      analyze_compile_perf.py
  .benchkit/                    # gitignored (DB + artifacts)
```

**`benchmarks/scripts/`** -- benchmark definitions with function, cases, and sweep. These are the record of what was run. Commit them, don't modify after running.

**`benchmarks/analysis/`** -- analysis and plotting. Disposable -- the agent can rewrite these to try different plots or aggregations. The data is safe in the DB.

Never put sweep and analysis in the same script. Re-running an analysis script must not trigger a new sweep.

## API

**Benchmark script** (`benchmarks/scripts/compile_perf.py`):

```python
"""Compare compile times of gcc vs clang across optimization levels."""

import benchkit as bk


@bk.func("compile-perf")
def compile_perf(compiler: str, opt_level: str) -> None:
    """Run compiler with 5 repetitions after warmup."""
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


# Compare gcc and clang across O0, O2, O3.
CASES = bk.grid(compiler=["gcc", "clang"], opt_level=["O0", "O2", "O3"])

if __name__ == "__main__":
    compile_perf.sweep(cases=CASES, max_workers=4, timeout=300)
# Rerun: uv run --group bench python benchmarks/scripts/compile_perf.py
```

**Analysis script** (`benchmarks/analysis/analyze_compile_perf.py`):

```python
"""Analyze and plot compile-perf results."""

import benchkit as bk
import matplotlib.pyplot as plt

analysis = bk.open_analysis("compile-perf")
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

Resume is ONLY for crashes or interruptions. Set the `BENCHKIT_SWEEP` env var:

```bash
BENCHKIT_SWEEP=20260322T143000000000Z uv run --group bench python benchmarks/scripts/compile_perf.py
```

The script itself never mentions sweep IDs. Never resume with changed code -- changed code = fresh sweep (the default).

## Workflow

**Never run an experiment without clear intent.** Before writing any code, state what you are measuring, why, and what you expect to learn. After every experiment, explain what you found -- do not just dump numbers.

1. **Intent** -- state what is being measured, why, and what outcome would be interesting. Get confirmation before proceeding if the goal is ambiguous.
2. **Implement** -- self-documenting benchmark script in `benchmarks/`.
3. **Execute** -- `.sweep(cases=...)`. Check `analysis.summary()` for failures.
4. **Analyze** -- `load_frame()`, aggregate with pandas, check for anomalies.
5. **Plot** -- publication-quality figures.
6. **Report** -- this is the most important step. Present a concise but complete summary:

   - What was the goal?
   - What cases were tested?
   - What are the key findings? (concrete numbers, not vague statements)
   - Are there surprises or anomalies?
   - What should be investigated next?

   Bad: "The results are in the database."
   Good: "clang O3 compiles 2.1x faster than gcc O3 (12ms vs 25ms, std < 1ms across 5 reps). Both compilers show diminishing returns past O2. Next: test with LTO."

7. **Journal** -- append your findings to the journal. **Every experiment gets journaled. No exceptions.**

## Journal

**Every experiment must be journaled. No exceptions. No deferring.**

The journal is a private research log that lives outside the project repo. It uses one file per experiment for easy navigation, cross-referencing, and compatibility with tools like Obsidian.

**Configuration:** `BENCHKIT_JOURNAL` points to the journal **directory**:

```bash
export BENCHKIT_JOURNAL=<path-to-journal-directory>
```

If `BENCHKIT_JOURNAL` is not set, **ask the user** for the journal directory path before running any experiment. Save it to a `.env` file in the project root (ensure `.env` is in `.gitignore`).

**Directory structure:**

```
$BENCHKIT_JOURNAL/
  index.md                              # project overview, updated after each experiment
  2026-03-22-compile-perf.md            # one file per experiment
  2026-03-22-compile-perf.png           # figures next to the entry
  2026-03-23-decoder-comparison.md
  2026-03-23-decoder-comparison.png
```

**Before running an experiment:** read `index.md` and scan filenames to understand what was already tried. Do not repeat experiments without reason.

**After every experiment:**

1. Create a new file `YYYY-MM-DD-<benchmark-id>.md`. If the file already exists (same experiment re-run on the same day), append a suffix: `YYYY-MM-DD-<benchmark-id>-2.md`.

2. Write the entry:

```markdown
# GCC vs Clang optimization levels

**Goal:** Compare compile times across optimization levels.
**Script:** `benchmarks/compile_perf.py`
**Cases:** 2 compilers x 3 opt levels x 5 reps = 30 rows.
**Related:** [[2026-03-20-compile-perf]] (previous run without O3)

| Compiler | O0  | O2   | O3   |
| -------- | --- | ---- | ---- |
| gcc      | 8ms | 18ms | 25ms |
| clang    | 6ms | 11ms | 12ms |

![Compile times](2026-03-22-compile-perf.png)

**Findings:**

- clang O3 is 2.1x faster than gcc O3 (12ms vs 25ms)
- Diminishing returns past O2 for both compilers

**Next:** Test with LTO enabled.
```

3. Update `index.md` with a one-line summary:

```markdown
# My Project -- Experiment Index

| Date       | Experiment                        | Key finding                      |
| ---------- | --------------------------------- | -------------------------------- |
| 2026-03-22 | [[2026-03-22-compile-perf]]       | clang O3 2.1x faster than gcc O3 |
| 2026-03-23 | [[2026-03-23-decoder-comparison]] | union-find decoder 3x faster     |
```

Rules:

- One file per experiment. Never edit old entries.
- Use `[[wikilinks]]` to cross-reference related experiments.
- Include tables when comparing configurations. Include figures when they clarify.
- Keep findings concise. One sentence per finding, concrete numbers.
- Figures are saved in the same directory, named to match the entry file.
