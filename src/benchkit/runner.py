"""Benchmark sweep runner with process-based parallelism."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import pickle  # noqa: S403
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    The benchmark function calls ``save_result()`` which writes directly to the DB.

    Returns:
        _CaseResult: The result of the case execution.

    Raises:
        ValueError: If the benchmark case did not produce results.
    """
    ctx = RunContext(
        sweep_id=sweep,
        case_key=case_key_value,
        benchmark_id=benchmark,
        artifact_dir_path=Path(artifact_dir),
        db_path=db_path,
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
            rep=0,
            status=RunStatus.FAILURE.value,
            config=case_config,
            metrics={},
            artifact_dir=artifact_dir,
            error={"type": type(exc).__name__, "message": str(exc)},
            env=capture_env(),
        )
        return _CaseResult(status=RunStatus.FAILURE, error=exc)

    # If save_result() was never called, try using the return value
    if not ctx._has_result:  # noqa: SLF001
        if isinstance(returned, dict):
            ctx.save_result(returned)
        else:
            msg = "Benchmark case did not produce results. Call bk.context().save_result({...}) or return a dict."
            raise ValueError(msg)

    return _CaseResult(status=RunStatus.OK, error=None)


def _handle_timeout(
    case: _Case,
    *,
    timeout: float,
    benchmark: str,
    sweep: str,
    artifact_dir: str,
    db_path: str,
) -> _CaseResult:
    """Record a timeout as a failed run in the database.

    Returns:
        _CaseResult: A failure result with TimeoutError.
    """
    store = BenchkitStore(path=Path(db_path))
    store.insert_run(
        benchmark=benchmark,
        sweep=sweep,
        case_key=case.case_key,
        rep=0,
        status=RunStatus.FAILURE.value,
        config=case.config,
        metrics={},
        artifact_dir=artifact_dir,
        error={"type": "TimeoutError", "message": f"Case exceeded {timeout}s timeout"},
        env=capture_env(),
    )
    return _CaseResult(
        status=RunStatus.FAILURE,
        error=TimeoutError(f"Case exceeded {timeout}s timeout"),
    )


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
    timeout: float | None = None

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

        if (self.max_workers > 1 and len(pending) > 1) or self.timeout is not None:
            self._run_with_pool(pending, sweep_id=sweep_id, store=store)
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
        total = len(cases)
        for i, case in enumerate(cases):
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
            self._log_progress(i + 1, total, self.id)

    def _run_with_pool(
        self,
        cases: list[_Case],
        *,
        sweep_id: str,
        store: BenchkitStore,
    ) -> None:
        pool_class = self._pick_pool_class()
        workers = max(self.max_workers, 1)
        label = self.id if workers == 1 else f"{self.id} ({workers}w)"
        total = len(cases)
        done = 0

        with pool_class(max_workers=workers) as pool:
            futures: dict[concurrent.futures.Future[_CaseResult], _Case] = {}
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
                case = futures[future]
                try:
                    result = future.result(timeout=self.timeout)
                except (TimeoutError, concurrent.futures.TimeoutError):
                    art_dir = str(
                        store.artifact_dir_for(
                            benchmark=self.id,
                            sweep=sweep_id,
                            case_key=case.case_key,
                        )
                    )
                    result = _handle_timeout(
                        case,
                        timeout=self.timeout or 0,
                        benchmark=self.id,
                        sweep=sweep_id,
                        artifact_dir=art_dir,
                        db_path=str(store.path),
                    )
                if result.error is not None and not self.continue_on_failure:
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise result.error
                done += 1
                self._log_progress(done, total, label)

    def _pick_pool_class(self) -> type[ProcessPoolExecutor | ThreadPoolExecutor]:
        """Choose the best executor class.

        Returns:
            type: ProcessPoolExecutor if the function is picklable, else ThreadPoolExecutor.
        """
        try:
            pickle.dumps(self.fn)
        except (pickle.PicklingError, AttributeError, TypeError):
            return ThreadPoolExecutor
        else:
            return ProcessPoolExecutor

    def _iter_cases(self) -> Iterator[_Case]:
        for config in self.cases:
            normalized = dict(config)
            yield _Case(
                config=normalized,
                case_key=case_key(benchmark_name=self.id, config=normalized),
            )

    def _log_progress(self, done: int, total: int, label: str) -> None:
        if self.show_progress:
            print(f"\r{label}: {done}/{total}", end="", flush=True)  # noqa: T201
            if done == total:
                print(flush=True)  # noqa: T201


def _generate_sweep_id() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
