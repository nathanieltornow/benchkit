"""Benchmark sweep runner with process-based parallelism."""

from __future__ import annotations

import datetime as dt
import pickle  # noqa: S403
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn

from .logging import RunStatus, capture_env
from .runtime import RunContext, activated_context
from .store import BenchkitStore, case_key, default_store

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class _Case:
    """Normalized benchmark case metadata."""

    config: dict[str, Any]
    case_key: str


@dataclass(frozen=True, slots=True)
class _CaseResult:
    """Result from one executed benchmark case."""

    status: RunStatus
    metrics: dict[str, Any]
    error: Exception | None


def _run_case_in_worker(
    fn: Callable[..., Any],
    case_config: dict[str, Any],
    case_key_value: str,
    *,
    benchmark: str,
    sweep: str,
    artifact_dir: str,
    db_path: str,
) -> _CaseResult:
    """Execute one benchmark case. Designed to run in a worker process.

    Each worker opens its own SQLite connection via WAL mode.

    Returns:
        _CaseResult: The result of the case execution.

    Raises:
        ValueError: If the benchmark case did not produce metrics.
    """
    ctx = RunContext(
        sweep_id=sweep,
        case_key=case_key_value,
        benchmark_id=benchmark,
        artifact_dir_path=Path(artifact_dir),
        config=dict(case_config),
    )

    try:
        with activated_context(ctx):
            returned = fn(**case_config)
    except Exception as exc:  # noqa: BLE001
        store = BenchkitStore(path=Path(db_path))
        store.insert_run(
            benchmark=benchmark,
            sweep=sweep,
            case_key=case_key_value,
            status=RunStatus.FAILURE.value,
            config=case_config,
            metrics={},
            artifact_dir=artifact_dir,
            error={"type": type(exc).__name__, "message": str(exc)},
            env=capture_env(),
        )
        return _CaseResult(status=RunStatus.FAILURE, metrics={}, error=exc)

    if ctx.result_row:
        metrics = dict(ctx.result_row)
    elif isinstance(returned, dict):
        metrics = dict(returned)
    else:
        msg = "Benchmark case did not produce metrics. Use bk.context().save_result(...) or return a dict."
        raise ValueError(msg)

    store = BenchkitStore(path=Path(db_path))
    store.insert_run(
        benchmark=benchmark,
        sweep=sweep,
        case_key=case_key_value,
        status=RunStatus.OK.value,
        config=case_config,
        metrics=metrics,
        artifact_dir=artifact_dir,
        env=capture_env(),
    )
    return _CaseResult(status=RunStatus.OK, metrics=metrics, error=None)


@dataclass(slots=True)
class SweepRunner:
    """Run benchmark cases sequentially or in parallel with ProcessPoolExecutor."""

    id: str
    fn: Callable[..., Any]
    cases: Sequence[Mapping[str, Any]]
    show_progress: bool = True
    max_workers: int = 1
    continue_on_failure: bool = True
    sweep: str | None = None

    def run(self) -> str:
        """Execute all pending cases and return the sweep ID used.

        Returns:
            str: The sweep identifier.
        """
        sweep_id = self.sweep or _generate_sweep_id()
        store = default_store()
        all_cases = list(self._iter_cases())
        completed = store.completed_keys(benchmark=self.id, sweep=sweep_id)
        pending = [c for c in all_cases if c.case_key not in completed]

        if not pending:
            return sweep_id

        if self.max_workers > 1 and len(pending) > 1:
            self._run_parallel(pending, sweep_id=sweep_id, store=store)
        else:
            self._run_sequential(pending, sweep_id=sweep_id, store=store)

        return sweep_id

    def _run_sequential(
        self,
        cases: list[_Case],
        *,
        sweep_id: str,
        store: BenchkitStore,
    ) -> None:
        progress_cm = self._progress(len(cases))
        with progress_cm as progress:
            task_id = progress.add_task(f"[cyan]{self.id}", total=len(cases)) if progress is not None else None
            for case in cases:
                art_dir = str(
                    store.artifact_dir_for(
                        benchmark=self.id,
                        sweep=sweep_id,
                        case_key=case.case_key,
                    )
                )
                result = _run_case_in_worker(
                    self.fn,
                    case.config,
                    case.case_key,
                    benchmark=self.id,
                    sweep=sweep_id,
                    artifact_dir=art_dir,
                    db_path=str(store.path),
                )
                if result.error is not None and not self.continue_on_failure:
                    raise result.error
                if progress is not None and task_id is not None:
                    progress.advance(task_id)

    def _run_parallel(
        self,
        cases: list[_Case],
        *,
        sweep_id: str,
        store: BenchkitStore,
    ) -> None:
        # Use ProcessPoolExecutor for real parallelism. Fall back to
        # ThreadPoolExecutor if the benchmark function can't be pickled
        # (e.g. lambdas, closures, or functions defined inside other functions).
        try:
            pickle.dumps(self.fn)
            pool_class = ProcessPoolExecutor
        except (pickle.PicklingError, AttributeError, TypeError):
            pool_class = ThreadPoolExecutor  # type: ignore[assignment]

        progress_cm = self._progress(len(cases))
        with progress_cm as progress:
            label = f"[cyan]{self.id} ({self.max_workers}w)"
            task_id = progress.add_task(label, total=len(cases)) if progress is not None else None

            with pool_class(max_workers=self.max_workers) as pool:
                futures = {}
                for case in cases:
                    art_dir = str(
                        store.artifact_dir_for(
                            benchmark=self.id,
                            sweep=sweep_id,
                            case_key=case.case_key,
                        )
                    )
                    future = pool.submit(
                        _run_case_in_worker,
                        self.fn,
                        case.config,
                        case.case_key,
                        benchmark=self.id,
                        sweep=sweep_id,
                        artifact_dir=art_dir,
                        db_path=str(store.path),
                    )
                    futures[future] = case

                for future in as_completed(futures):
                    result = future.result()
                    if result.error is not None and not self.continue_on_failure:
                        pool.shutdown(wait=False, cancel_futures=True)
                        raise result.error
                    if progress is not None and task_id is not None:
                        progress.advance(task_id)

    def _iter_cases(self) -> Iterator[_Case]:
        for config in self.cases:
            normalized = dict(config)
            yield _Case(
                config=normalized,
                case_key=case_key(benchmark_name=self.id, config=normalized),
            )

    def _progress(self, total: int) -> Progress | nullcontext[None]:
        if not self.show_progress or total == 0:
            return nullcontext(None)
        return Progress(
            SpinnerColumn(),
            TextColumn(f"[bold]{self.id}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            transient=True,
        )


def _generate_sweep_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
