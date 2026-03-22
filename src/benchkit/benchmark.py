"""Function-first benchmark execution API."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import asdict, dataclass, is_dataclass
from itertools import product
from typing import TYPE_CHECKING, Any

from .analysis import Analysis
from .runner import SweepRunner
from .store import default_store

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from .logging import Run


def _sweep_id_for_cases(benchmark_id: str, cases: list[dict[str, Any]]) -> str:
    """Derive a deterministic sweep ID from the benchmark and case list.

    Same benchmark + same cases = same sweep ID = automatic resume.
    Different cases = different sweep ID = fresh run.

    Returns:
        str: A stable sweep identifier.
    """
    payload = json.dumps(
        {"benchmark": benchmark_id, "cases": sorted(cases, key=lambda c: json.dumps(c, sort_keys=True))},
        default=str,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _normalize_case(case: object) -> dict[str, Any]:
    """Convert one case object into a JSON-serializable dict.

    Returns:
        dict[str, Any]: The normalized case dictionary.

    Raises:
        TypeError: If the case type is not supported.
    """
    if isinstance(case, dict):
        return {str(k): v for k, v in case.items()}
    if is_dataclass(case) and not isinstance(case, type):
        return dict(asdict(case))
    if hasattr(case, "__dict__"):
        return {key: value for key, value in vars(case).items() if not key.startswith("_")}
    msg = "Benchmark cases must be mappings, dataclass instances, or objects with a __dict__."
    raise TypeError(msg)


def grid(**params: Iterable[Any]) -> list[dict[str, Any]]:
    """Expand a Cartesian product of parameters into explicit case dicts.

    Returns:
        list[dict[str, Any]]: The expanded case list.
    """
    if not params:
        return [{}]
    names = tuple(params.keys())
    values = [list(options) for options in params.values()]
    return [dict(zip(names, combination, strict=True)) for combination in product(*values)]


@dataclass(frozen=True, slots=True)
class BenchFunction:
    """Decorated benchmark function with direct-call and sweep execution."""

    id: str
    fn: Callable[..., Any]

    def __call__(self, *args: object, **kwargs: object) -> Run:
        """Run a single benchmark case.

        Returns:
            Run: The completed run.
        """
        case = self._bind_case(*args, **kwargs)
        # Use latest sweep so consecutive single calls accumulate in the same sweep
        latest = default_store().latest_sweep(self.id)
        analysis = self.sweep(cases=[case], sweep=latest, show_progress=False)
        return analysis.get_run(config=case)

    def sweep(
        self,
        *,
        cases: Sequence[Any],
        new_sweep: bool = False,
        sweep: str | None = None,
        show_progress: bool = True,
        max_workers: int = 1,
        timeout: float | None = None,
    ) -> Analysis:
        """Run an explicit case list in the current or a fresh sweep.

        Args:
            cases: Explicit list of case dicts, dataclass instances, or objects.
            new_sweep: Force a fresh sweep even if one exists.
            sweep: Use a specific sweep id.
            show_progress: Show a progress bar during execution.
            max_workers: Number of concurrent worker processes. 1 = sequential.
            timeout: Maximum seconds per case. Cases exceeding this are recorded
                as failures with ``TimeoutError``. None means no limit.

        Returns:
            Analysis: Read-only handle for the completed sweep.
        """
        normalized_cases = [_normalize_case(case) for case in cases]

        if sweep is not None:
            resolved_sweep = sweep
        elif new_sweep:
            resolved_sweep = None
        else:
            # Deterministic sweep ID from cases: same cases = resume, different cases = new sweep
            resolved_sweep = _sweep_id_for_cases(self.id, normalized_cases)

        runner = SweepRunner(
            id=self.id,
            fn=self.fn,
            cases=normalized_cases,
            show_progress=show_progress,
            max_workers=max_workers,
            sweep=resolved_sweep,
            timeout=timeout,
        )
        actual_sweep = runner.run()
        return Analysis(id=self.id, sweep=actual_sweep)

    def _bind_case(self, *args: object, **kwargs: object) -> dict[str, Any]:
        bound = inspect.signature(self.fn).bind(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)


def func(benchmark_id: str) -> Callable[[Callable[..., Any]], BenchFunction]:
    """Decorate a Python function as a BenchKit benchmark.

    Returns:
        Callable: The decorator function.
    """

    def decorator(fn: Callable[..., Any]) -> BenchFunction:
        return BenchFunction(id=benchmark_id, fn=fn)

    return decorator
