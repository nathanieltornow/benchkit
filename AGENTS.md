# Agent Notes

Use `benchkit` as a local library for benchmark orchestration, result logging, and plot generation.

## Recommended pattern

1. Import `benchkit as bk`.
2. Put the benchmark body in a pure function that returns a JSON-serializable dict.
3. Stack decorators in this order when possible:
   `@bk.foreach(...)`, `@bk.retry(...)`, `@bk.timeout(...)`, `@bk.catch_failures(...)`, `@bk.log(...)`
4. Execute the function once to run the sweep.
5. Read results with `bk.load_log(...)`.
6. Plot from the resulting dataframe and save with `@bk.pplot(...)` or `bk.pplot(...)(...)`.

## Conventions

- Relative log paths are written to `.benchkit/logs/`.
- Artifacts are written to `.benchkit/artifacts/`.
- Cached values are written to `.benchkit/cache/`.
- Plots are written to `.benchkit/plots/`.
- Set `BENCHKIT_HOME` to move all of those directories.

## Return shapes

- Prefer flat metric dicts such as `{"runtime_ms": 12.3, "accuracy": 0.94}`.
- Avoid returning custom classes unless they stringify cleanly in logs.
- Use `bk.artifact(...)` for large binary outputs and log the returned path instead of embedding bytes in results.

## Plotting

- `bk.bar_comparison(...)`, `bk.line_comparison(...)`, and `bk.scatter_comparison(...)` expect a pandas dataframe.
- With normalized logs, use columns like `config.batch_size` and `result.runtime_ms`.
- `bk.pplot(...)` saves timestamped figures automatically.

## Failure handling

- `bk.retry(n)` retries exceptions.
- `bk.timeout(seconds, default=...)` runs the function in a worker subprocess and returns the provided default on timeout.
- `bk.catch_failures(default=...)` converts exceptions into a fallback result so the sweep can continue.

## Common mistake to avoid

- `foreach` zips values inside one decorator call. For a Cartesian product, stack multiple `foreach` decorators instead of passing multiple keyword lists to one decorator.
