# Agent Notes

Use `benchkit` as a local library for benchmark orchestration, JSONL run logging, and plot generation.

## Recommended pattern

1. Import `benchkit as bk`.
2. Put the benchmark body in a pure function that returns a JSON-serializable dict.
3. Prefer `bk.Sweep(id=..., fn=..., params=..., repeat=5)` for repeated parameter sweeps.
4. Use `Sweep` options like `retries=...`, `timeout_seconds=...`, and `continue_on_failure=True` for run reliability.
5. Execute the sweep once to generate the full benchmark log.
6. Read results with `bk.load_log(...)`.
7. If the sweep stores artifacts, fetch them with `bk.get_artifact(...)` or inspect them with `bk.list_artifacts(...)`.
8. Create figures inside `with bk.pplot(...):` and save them with `bk.save_figure(...)`.
9. Use the `benchkit` CLI for operational tasks like watching logs and resolving artifacts.

## Conventions

- Relative log paths are written to JSONL files under `~/.benchkit/logs/`.
- Artifacts are written to `~/.benchkit/artifacts/`.
- If a sweep function calls `bk.context()`, per-case artifacts go under `~/.benchkit/artifacts/<id>/<case-key>/rep-<n>/`.
- Plots are written to `~/.benchkit/plots/`.
- Sweep resume state is cached per sweep id under `~/.benchkit/state/<id>.sqlite` by default.
- Sweep logs include `benchmark`, `sweep_id`, `rep`, `rep_count`, `status`, `attempt`, `execution_mode`, and `max_workers`.
- Set `BENCHKIT_HOME` to move all of those directories.

## Return shapes

- Prefer flat metric dicts such as `{"runtime_ms": 12.3, "accuracy": 0.94}`.
- Avoid returning custom classes unless they stringify cleanly in logs.
- For sweep-local files, prefer `bk.context().save_json(...)`, `bk.context().save_text(...)`, `bk.context().save_bytes(...)`, or `bk.context().copy_file(...)`.
- For Python objects, prefer `bk.context().save_pickle(...)` and load them back with `bk.load_pickle(...)`.

## Plotting

- `bk.bar_comparison(...)`, `bk.line_comparison(...)`, and `bk.scatter_comparison(...)` expect a pandas dataframe.
- With normalized logs, use columns like `config.batch_size` and `result.runtime_ms`.
- `bk.pplot(...)` applies the default plotting style.
- `bk.save_figure(...)` saves timestamped figures automatically.

## Failure handling

- `bk.Sweep(...)` supports `retries=...`, `timeout_seconds=...`, `continue_on_failure=True`, `default_result=...`, `max_workers=...`, and `resume=True`.
- Use `max_workers=1` for timing-sensitive benchmarks unless the user explicitly accepts contention.
