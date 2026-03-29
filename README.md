# benchkit

Benchmark sweeps with parallel execution and resume support. Works with any workload -- Python, Rust, C++, shell scripts.

## Install

```bash
uv add --group bench git+https://github.com/nathanieltornow/benchkit@v0.0.2
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

# Run all cases
compile_benchmark.sweep(cases=CASES, max_workers=4, timeout=300)

# Get results as a DataFrame
df = bk.load_frame("compile-benchmark")
```

## CLI

```bash
benchkit sweeps                          # list all sweeps
benchkit runs compile-benchmark          # list runs
benchkit runs compile-benchmark --status ok
```
