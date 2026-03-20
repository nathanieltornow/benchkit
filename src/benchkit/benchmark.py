"""Function-first benchmark execution API."""

from __future__ import annotations

import datetime as dt
import inspect
from dataclasses import asdict, dataclass, is_dataclass
from itertools import product
from typing import TYPE_CHECKING, Any

from .analysis import Analysis, open_analysis
from .artifacts import context
from .runner import SweepRunner
from .store import BenchkitStore, log_execution_event

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from .logging import Run


def _normalize_case(case: object) -> dict[str, Any]:
    """Convert one case object into a JSON-serializable dict.

    Returns:
        dict[str, Any]: Normalized case mapping.

    Raises:
        TypeError: If the case object cannot be normalized.
    """
    if isinstance(case, dict):
        return dict(case)
    if is_dataclass(case) and not isinstance(case, type):
        return dict(asdict(case))
    if hasattr(case, "__dict__"):
        return {key: value for key, value in vars(case).items() if not key.startswith("_")}
    msg = "Benchmark cases must be mappings, dataclass instances, or objects with a __dict__."
    raise TypeError(msg)


def grid(**params: Iterable[Any]) -> list[dict[str, Any]]:
    """Expand a Cartesian product of parameters into explicit case dicts.

    Returns:
        list[dict[str, Any]]: Explicit case mappings.
    """
    if not params:
        return [{}]
    names = tuple(params.keys())
    values = [list(options) for options in params.values()]
    return [dict(zip(names, combination, strict=True)) for combination in product(*values)]


@dataclass(frozen=True, slots=True)
class BenchFunction:
    """Decorated benchmark function with direct-call and sweep execution helpers."""

    id: str
    fn: Callable[..., Any]

    def __call__(self, *args: object, **kwargs: object) -> Run:
        """Run a single benchmark case.

        Returns:
            Run: The stored run for this benchmark invocation.
        """
        case = self._bind_case(*args, **kwargs)
        analysis = self.sweep(cases=[case], show_progress=False)
        return analysis.get_run(config=case, rep=1)

    def sweep(
        self,
        *,
        cases: Sequence[Any],
        new_sweep: bool = False,
        sweep: str | None = None,
        timeout_seconds: float | None = None,
        max_workers: int = 1,
        show_progress: bool = True,
    ) -> Analysis:
        """Run an explicit case list in the current or a fresh sweep.

        Returns:
            Analysis: Read-only handle for the completed sweep.
        """
        normalized_cases = [_normalize_case(case) for case in cases]
        resolved_sweep = self._resolve_sweep(sweep=sweep, new_sweep=new_sweep)
        storage_id = f"{self.id}--{resolved_sweep}"
        runner = SweepRunner(
            id=storage_id,
            fn=self._run_case_kwargs,
            cases=normalized_cases,
            benchmark_id=self.id,
            sweep=resolved_sweep,
            timeout_seconds=timeout_seconds,
            max_workers=max_workers,
            show_progress=show_progress,
        )
        log_execution_event(event="benchmark_started", benchmark_id=self.id, sweep_id=resolved_sweep)
        runner.run()
        analysis = open_analysis(self.id, sweep=resolved_sweep)
        BenchkitStore().index_runs(
            benchmark_id=self.id,
            sweep_id=resolved_sweep,
            storage_id=storage_id,
            runs=analysis.load_runs(),
        )
        log_execution_event(
            event="benchmark_finished",
            benchmark_id=self.id,
            sweep_id=resolved_sweep,
            payload={"storage_id": storage_id},
        )
        return analysis

    def _bind_case(self, *args: object, **kwargs: object) -> dict[str, Any]:
        bound = inspect.signature(self.fn).bind(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)

    def _resolve_sweep(self, *, sweep: str | None, new_sweep: bool) -> str:
        if sweep is not None:
            return sweep
        registry = BenchkitStore()
        current = registry.current_sweep(self.id)
        if new_sweep or current is None:
            return registry.create_sweep(
                benchmark_id=self.id,
                source_path=f"decorated:{self.fn.__module__}.{self.fn.__name__}",
            )
        return current

    def _run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        ctx = context()
        ctx.config = dict(case)
        try:
            returned = self.fn(**case)
        except Exception as exc:
            ctx.save_json(
                "metadata.json",
                {
                    "run_id": str(ctx.run_id),
                    "sweep_id": ctx.sweep_id,
                    "case_key": ctx.case_key,
                    "rep": ctx.rep,
                    "status": "failure",
                    "config": dict(case),
                    "artifact_dir": str(ctx.artifact_dir),
                    "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            raise

        if ctx.result_row:
            metrics = dict(ctx.result_row)
        elif isinstance(returned, dict):
            metrics = dict(returned)
        else:
            msg = "Benchmark case did not produce metrics. Use bk.context().save_result(...) or return a dict."
            raise ValueError(msg)
        ctx.save_result(metrics)
        ctx.save_json(
            "metadata.json",
            {
                "run_id": str(ctx.run_id),
                "sweep_id": ctx.sweep_id,
                "case_key": ctx.case_key,
                "rep": ctx.rep,
                "status": "ok",
                "config": dict(case),
                "artifact_dir": str(ctx.artifact_dir),
                "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "error_type": None,
                "error_message": None,
            },
        )
        return metrics

    def _run_case_kwargs(self, **case: object) -> dict[str, Any]:
        return self._run_case(dict(case))


def func(benchmark_id: str) -> Callable[[Callable[..., Any]], BenchFunction]:
    """Decorate a Python function as a BenchKit benchmark.

    Returns:
        Callable[[Callable[..., Any]], BenchFunction]: Decorator that wraps the benchmark function.
    """

    def decorator(fn: Callable[..., Any]) -> BenchFunction:
        return BenchFunction(id=benchmark_id, fn=fn)

    return decorator
