# benchkit

Benchmark sweeps with automatic resume, parallel execution, and publication-quality plotting. Works with any workload -- Python, Rust, C++, shell scripts.

## Install

```bash
uv add git+https://github.com/nathanieltornow/benchkit@v0.0.1
benchkit init  # install Claude Code skills
```

## Example

```python
import benchkit as bk


@bk.func("compile-benchmark")
def compile_benchmark(compiler: str, opt_level: str) -> None:
    result = bk.run(
        [compiler, f"-{opt_level}", "-o", "/dev/null", "bench.c"],
        name="compile",
        timeout=120,
    )
    bk.context().save_result({"time_ms": 12.5, "returncode": result.returncode})


CASES = bk.grid(compiler=["gcc", "clang"], opt_level=["O0", "O2", "O3"])

# Run all cases (resumes automatically if interrupted)
analysis = compile_benchmark.sweep(cases=CASES, max_workers=4, timeout=300)

# Analyze
df = analysis.load_frame()
run = analysis.get_run(config={"compiler": "gcc", "opt_level": "O0"})
print(run.metrics)

# Plot
with bk.pplot(preset="double-column", latex=True):
    fig, ax = plt.subplots()
    ...
analysis.save_figure(fig, plot_name="compile-times")
```

## CLI

```bash
benchkit sweeps                          # list all sweeps
benchkit runs compile-benchmark          # list runs
benchkit runs compile-benchmark --status ok
```
