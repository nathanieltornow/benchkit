"""Explicit benchmark sweep runner."""

from __future__ import annotations

import datetime as dt
import inspect
import multiprocessing as mp
import queue
import random
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from itertools import product
from typing import TYPE_CHECKING, Any, TypeVar, cast

import cloudpickle  # type: ignore[import-not-found]
from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from .artifacts import ArtifactIndex, RunContext, activated_context
from .config import resolve_output_path
from .logging import write_log_entry
from .state import SweepState, case_key, state_path_for

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping
    from multiprocessing.context import SpawnContext, SpawnProcess
    from multiprocessing.queues import Queue
    from pathlib import Path

R = TypeVar("R")
console = Console()


@dataclass(frozen=True, slots=True)
class _Case:
    rep: int
    config: dict[str, Any]
    log_config: dict[str, Any]
    case_key: str


@dataclass(frozen=True, slots=True)
class _CaseResult:
    result: Any
    outcome: dict[str, Any]
    artifacts: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class _ActiveCase:
    worker_id: int
    index: int
    case: _Case
    attempt: int
    started_at: float


@dataclass(slots=True)
class _WorkerState:
    worker_id: int
    proc: SpawnProcess
    job_queue: Queue[Any]


@dataclass(frozen=True, slots=True)
class _Job:
    case: _Case
    index: int
    attempt: int


def _run_case_once(
    fn: Callable[..., Any],
    case: _Case,
    *,
    sweep_id: str,
) -> tuple[Any, list[dict[str, Any]], None] | tuple[None, list[dict[str, Any]], Exception]:
    ctx = RunContext(sweep_id=sweep_id, case_key=case.case_key, rep=case.rep)
    try:
        with activated_context(ctx):
            result = fn(**case.config)
    except Exception as exc:  # noqa: BLE001
        return None, ctx.records, exc
    return result, ctx.records, None


def _pool_worker_entry(
    fn_bytes: bytes,
    sweep_id: str,
    worker_id: int,
    job_queue: Queue[Any],
    result_queue: Queue[Any],
) -> None:
    fn: Callable[..., Any] = cloudpickle.loads(fn_bytes)
    while True:
        job = job_queue.get()
        if job == "STOP":
            return
        assert isinstance(job, _Job)
        result_queue.put(("started", worker_id, job.index, job.attempt))
        result, artifacts, exc = _run_case_once(
            fn,
            job.case,
            sweep_id=sweep_id,
        )
        if exc is not None:
            result_queue.put(("result", worker_id, job.index, job.attempt, False, exc, artifacts))
            continue
        result_queue.put(("result", worker_id, job.index, job.attempt, True, result, artifacts))


def _run_case_with_retries(
    fn: Callable[..., Any],
    case: _Case,
    retries: int,
    *,
    sweep_id: str,
    continue_on_failure: bool,
    default_result: Any,  # noqa: ANN401
) -> _CaseResult:
    for attempt in range(1, retries + 1):
        result, artifacts, exc = _run_case_once(
            fn,
            case,
            sweep_id=sweep_id,
        )
        if exc is None:
            return _CaseResult(
                result=result,
                outcome={"status": "ok", "attempt": attempt},
                artifacts=artifacts,
            )
        if attempt < retries:
            continue
        if not continue_on_failure:
            raise exc
        return _CaseResult(
            result=default_result,
            outcome={
                "status": "failure",
                "attempt": attempt,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            artifacts=artifacts,
        )

    msg = "unreachable retry state"
    raise AssertionError(msg)


@dataclass(slots=True)
class Sweep:
    """Run a Cartesian-product parameter sweep with repeated trials."""

    id: str
    fn: Callable[..., Any]
    params: Mapping[str, Iterable[Any]] = field(default_factory=dict)
    repeat: int = 1
    log_path: Path | str | None = None
    shuffle: bool = False
    seed: int | None = None
    retries: int = 1
    timeout_seconds: float | None = None
    continue_on_failure: bool = True
    default_result: Any = None
    max_workers: int = 1
    show_progress: bool = True
    resume: bool = True
    state_path: Path | None = None

    def __post_init__(self) -> None:
        """Validate the sweep configuration.

        Raises:
            ValueError: If ``repeat``, ``retries``, or ``max_workers`` are
                smaller than 1, or if ``timeout_seconds`` is not positive.
        """
        if self.repeat < 1:
            msg = "repeat must be at least 1"
            raise ValueError(msg)
        if not self.id.strip():
            msg = "id must not be empty"
            raise ValueError(msg)
        if self.retries < 1:
            msg = "retries must be at least 1"
            raise ValueError(msg)
        if self.max_workers < 1:
            msg = "max_workers must be at least 1"
            raise ValueError(msg)
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            msg = "timeout_seconds must be > 0"
            raise ValueError(msg)
        if self.log_path is None:
            self.log_path = f"{self.id}.jsonl"
        if self.state_path is None:
            self.state_path = state_path_for(self.id)

    def run(self) -> list[R]:
        """Execute the benchmark function over all parameter combinations.

        Returns:
            list[R]: Results in execution order.
        """
        init_time = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        benchmark_name = self.id
        fn_name = self.fn.__name__
        all_cases = list(self._cases(self.fn, benchmark_name))
        state = SweepState(cast("Path", self.state_path))
        log_path = str(resolve_output_path(cast("str | Path", self.log_path), "logs"))
        existing_log_rows = self._count_existing_rows(log_path)
        completed_keys = (
            state.completed_keys(benchmark_name=benchmark_name, log_path=log_path) if self.resume else set()
        )
        cases = [case for case in all_cases if case.case_key not in completed_keys]
        skipped_count = len(all_cases) - len(cases)
        self._print_start(
            benchmark_name,
            len(cases),
            skipped_count,
            self.id,
            existing_log_rows,
        )

        if self.max_workers == 1 and self.timeout_seconds is None:
            results, _outcomes, _recent_cases = self._run_sequential(
                cases,
                cast("Callable[..., R]", self.fn),
                benchmark_name,
                self.id,
                fn_name,
                init_time,
                state,
                log_path,
            )
        else:
            results, _outcomes, _recent_cases = self._run_managed(
                cases,
                cast("Callable[..., R]", self.fn),
                benchmark_name,
                self.id,
                fn_name,
                init_time,
                state,
                log_path,
            )

        return results

    def _run_sequential(
        self,
        cases: list[_Case],
        fn: Callable[..., R],
        benchmark_name: str,
        sweep_id: str,
        func_name: str,
        init_time: str,
        state: SweepState,
        log_path: str,
    ) -> tuple[list[R], list[dict[str, Any]], list[tuple[_Case, _CaseResult]]]:
        results: list[R] = []
        outcomes: list[dict[str, Any]] = []
        counts = self._initial_counts()

        with self._live_dashboard() as progress:
            task_id = self._add_task(progress, benchmark_name, len(cases), counts)
            for case in cases:
                case_result = _run_case_with_retries(
                    fn,
                    case,
                    self.retries,
                    sweep_id=sweep_id,
                    continue_on_failure=self.continue_on_failure,
                    default_result=self.default_result,
                )
                results.append(cast("R", case_result.result))
                outcomes.append(case_result.outcome)
                self._update_counts(counts, case_result)
                self._log_case(
                    case,
                    case_result,
                    benchmark_name,
                    sweep_id,
                    func_name,
                    init_time,
                    state,
                    log_path,
                )
                self._advance(progress, task_id, counts)

        return results, outcomes, []

    def _run_managed(
        self,
        cases: list[_Case],
        fn: Callable[..., R],
        benchmark_name: str,
        sweep_id: str,
        func_name: str,
        init_time: str,
        state: SweepState,
        log_path: str,
    ) -> tuple[list[R], list[dict[str, Any]], list[Any]]:
        fn_bytes = cloudpickle.dumps(fn)
        ctx: SpawnContext = mp.get_context("spawn")
        result_queue: Queue[Any] = ctx.Queue()
        results_by_index: dict[int, R] = {}
        outcomes_by_index: dict[int, dict[str, Any]] = {}
        counts = self._initial_counts()
        active_by_worker: dict[int, _ActiveCase] = {}
        attempts_by_index: dict[int, int] = {}
        pending = list(enumerate(cases))
        idle_workers: list[int] = []
        workers = self._start_worker_pool(
            ctx,
            fn_bytes,
            sweep_id,
            result_queue,
        )
        worker_map = {worker.worker_id: worker for worker in workers}
        idle_workers = [worker.worker_id for worker in workers]

        with self._live_dashboard() as progress:
            task_id = self._add_task(progress, benchmark_name, len(cases), counts)
            while pending or active_by_worker or len(idle_workers) < len(workers):
                while pending and idle_workers:
                    index, case = pending.pop(0)
                    worker_id = idle_workers.pop(0)
                    attempt = attempts_by_index.get(index, 0) + 1
                    attempts_by_index[index] = attempt
                    worker_map[worker_id].job_queue.put(_Job(case=case, index=index, attempt=attempt))

                try:
                    message = result_queue.get(timeout=0.05)
                    event = message[0]
                    if event == "started":
                        _, worker_id, index, attempt = message
                        active_by_worker[worker_id] = _ActiveCase(
                            worker_id=worker_id,
                            index=index,
                            case=cases[index],
                            attempt=attempt,
                            started_at=time.monotonic(),
                        )
                        continue
                    _, worker_id, index, attempt, success, payload, artifacts = message
                    active_case = active_by_worker.get(worker_id)
                    if active_case is None or active_case.index != index or active_case.attempt != attempt:
                        continue
                    active_by_worker.pop(worker_id, None)
                    idle_workers.append(worker_id)
                    case_result = self._finalize_result(
                        success=success,
                        payload=payload,
                        attempt=attempt,
                        artifacts=artifacts,
                    )
                    case = active_case.case
                    results_by_index[index] = cast("R", case_result.result)
                    outcomes_by_index[index] = case_result.outcome
                    self._update_counts(counts, case_result)
                    self._log_case(
                        case,
                        case_result,
                        benchmark_name,
                        sweep_id,
                        func_name,
                        init_time,
                        state,
                        log_path,
                    )
                    self._advance(progress, task_id, counts)
                except queue.Empty:
                    pass

                self._check_timeouts(
                    active_by_worker,
                    results_by_index,
                    outcomes_by_index,
                    counts,
                    benchmark_name,
                    sweep_id,
                    func_name,
                    init_time,
                    state,
                    log_path,
                    progress,
                    task_id,
                    ctx,
                    fn_bytes,
                    sweep_id,
                    result_queue,
                    worker_map,
                    idle_workers,
                    attempts_by_index,
                )

        self._stop_worker_pool(workers)

        return (
            [results_by_index[index] for index in range(len(cases))],
            [outcomes_by_index[index] for index in range(len(cases))],
            [],
        )

    def _log_case(
        self,
        case: _Case,
        case_result: _CaseResult,
        benchmark_name: str,
        sweep_id: str,
        func_name: str,
        init_time: str,
        state: SweepState,
        log_path: str,
    ) -> None:
        updated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        attempt = int(case_result.outcome.get("attempt", 1))
        write_log_entry(
            cast("str | Path", self.log_path),
            config=case.log_config,
            result=case_result.result,
            func_name=func_name,
            init_time=init_time,
            extra={
                "benchmark": benchmark_name,
                "sweep_id": sweep_id,
                "rep": case.rep,
                "rep_count": self.repeat,
                "execution_mode": "parallel" if self.max_workers > 1 else "sequential",
                "max_workers": self.max_workers,
                "artifacts": case_result.artifacts,
                **case_result.outcome,
            },
        )
        ArtifactIndex().record_many(
            sweep_id=sweep_id,
            case_key=case.case_key,
            rep=case.rep,
            attempt=attempt,
            config=case.log_config,
            artifacts=case_result.artifacts,
        )
        state.record_case(
            case_key=case.case_key,
            benchmark_name=benchmark_name,
            rep=case.rep,
            status=str(case_result.outcome.get("status", "ok")),
            config=case.log_config,
            log_path=log_path,
            updated_at=updated_at,
        )

    def _start_worker_pool(
        self,
        ctx: SpawnContext,
        fn_bytes: bytes,
        sweep_id: str,
        result_queue: Queue[Any],
    ) -> list[_WorkerState]:
        workers: list[_WorkerState] = []
        for worker_id in range(self.max_workers):
            job_queue: Queue[Any] = ctx.Queue()
            proc = ctx.Process(
                target=_pool_worker_entry,
                args=(fn_bytes, sweep_id, worker_id, job_queue, result_queue),
            )
            proc.start()
            workers.append(_WorkerState(worker_id=worker_id, proc=proc, job_queue=job_queue))
        return workers

    @staticmethod
    def _stop_worker_pool(workers: list[_WorkerState]) -> None:
        for worker in workers:
            with suppress(Exception):
                worker.job_queue.put("STOP")
        for worker in workers:
            worker.proc.join(timeout=1)
            if worker.proc.is_alive():
                worker.proc.terminate()
                worker.proc.join()

    def _finalize_result(
        self,
        *,
        success: bool,
        payload: Any,  # noqa: ANN401
        attempt: int,
        artifacts: list[dict[str, Any]],
    ) -> _CaseResult:
        if success:
            return _CaseResult(
                result=payload,
                outcome={"status": "ok", "attempt": attempt},
                artifacts=artifacts,
            )

        if not self.continue_on_failure:
            raise payload

        return _CaseResult(
            result=self.default_result,
            outcome={
                "status": "failure",
                "attempt": attempt,
                "error_type": type(payload).__name__,
                "error_message": str(payload),
            },
            artifacts=artifacts,
        )

    def _check_timeouts(
        self,
        active: dict[int, _ActiveCase],
        results_by_index: dict[int, R],
        outcomes_by_index: dict[int, dict[str, Any]],
        counts: dict[str, int],
        benchmark_name: str,
        sweep_id: str,
        func_name: str,
        init_time: str,
        state: SweepState,
        log_path: str,
        progress: Progress | None,
        task_id: int | None,
        ctx: SpawnContext,
        fn_bytes: bytes,
        worker_sweep_id: str,
        result_queue: Queue[Any],
        worker_map: dict[int, _WorkerState],
        idle_workers: list[int],
        attempts_by_index: dict[int, int],
    ) -> None:
        if self.timeout_seconds is None:
            return

        now = time.monotonic()
        timed_out = [
            (worker_id, active_case)
            for worker_id, active_case in list(active.items())
            if (now - active_case.started_at) > self.timeout_seconds
        ]

        for worker_id, active_case in timed_out:
            worker = worker_map[worker_id]
            worker.proc.terminate()
            worker.proc.join()
            active.pop(worker_id, None)
            replacement_queue: Queue[Any] = ctx.Queue()
            replacement = ctx.Process(
                target=_pool_worker_entry,
                args=(
                    fn_bytes,
                    worker_sweep_id,
                    worker_id,
                    replacement_queue,
                    result_queue,
                ),
            )
            replacement.start()
            worker_map[worker_id] = _WorkerState(worker_id=worker_id, proc=replacement, job_queue=replacement_queue)
            if active_case.attempt < self.retries:
                attempts_by_index[active_case.index] = active_case.attempt + 1
                worker_map[worker_id].job_queue.put(
                    _Job(
                        case=active_case.case,
                        index=active_case.index,
                        attempt=active_case.attempt + 1,
                    )
                )
                idle_workers[:] = [wid for wid in idle_workers if wid != worker_id]
                continue

            idle_workers.append(worker_id)

            if not self.continue_on_failure:
                msg = f"Benchmark timed out after {self.timeout_seconds} seconds"
                raise TimeoutError(msg)

            case_result = _CaseResult(
                result=self.default_result,
                outcome={
                    "status": "timeout",
                    "attempt": active_case.attempt,
                    "error_type": "TimeoutError",
                    "error_message": f"Benchmark timed out after {self.timeout_seconds} seconds",
                },
                artifacts=[],
            )
            results_by_index[active_case.index] = cast("R", case_result.result)
            outcomes_by_index[active_case.index] = case_result.outcome
            self._update_counts(counts, case_result)
            self._log_case(
                active_case.case,
                case_result,
                benchmark_name,
                sweep_id,
                func_name,
                init_time,
                state,
                log_path,
            )
            self._advance(progress, task_id, counts)

    def _print_start(
        self,
        benchmark_name: str,
        total_cases: int,
        skipped_count: int,
        sweep_id: str,
        existing_log_rows: int,
    ) -> None:
        if not self.show_progress:
            return
        log_path = resolve_output_path(cast("str | Path", self.log_path), "logs")
        state_path = self.state_path
        mode = "parallel" if self.max_workers > 1 else "sequential"
        table = Table.grid(expand=True)
        table.add_column(ratio=1)
        table.add_column(justify="right")
        title = Text.assemble(
            ("sweep", "bold cyan"),
            ("  ", ""),
            (benchmark_name, "bold"),
        )
        meta = Text.assemble(
            (f"id {sweep_id}", "dim"),
            ("   ", ""),
            (mode, "magenta"),
            ("   ", ""),
            (f"{self.max_workers} workers", "yellow"),
            ("   ", ""),
            (f"repeat {self.repeat}", "green"),
        )
        counts = Text.assemble(
            (f"{total_cases}", "bold"),
            (" to run", "dim"),
            ("   ", ""),
            (f"{skipped_count}", "bold"),
            (" skipped", "dim"),
        )
        paths = Text.assemble(
            ("log ", "dim"),
            (str(log_path), "default"),
            ("   ", ""),
            (str(existing_log_rows), "bold"),
            (" existing rows", "dim"),
        )
        if self.resume:
            paths.append("\n")
            paths.append("state ", style="dim")
            paths.append(str(state_path), style="default")
        table.add_row(title, counts)
        table.add_row(meta, "")
        table.add_row(paths, "")
        console.print(
            Panel(
                table,
                box=ROUNDED,
                border_style="bright_black",
                padding=(0, 1),
            )
        )

    @contextmanager
    def _live_dashboard(self) -> Any:  # noqa: ANN401
        if not self.show_progress:
            yield None
            return
        progress = Progress(
            SpinnerColumn(style="bright_cyan"),
            TextColumn("[bold]{task.description}"),
            BarColumn(complete_style="cyan", finished_style="green", pulse_style="bright_black"),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TextColumn("{task.fields[counts]}", justify="left"),
            console=console,
        )
        with progress:
            yield progress

    @staticmethod
    def _add_task(
        progress: Progress | None,
        benchmark_name: str,
        total_cases: int,
        counts: dict[str, int],
    ) -> int | None:
        if progress is None:
            return None
        return cast(
            "int",
            progress.add_task(
                f"Running {benchmark_name}",
                total=total_cases,
                counts=Sweep._counts_text(counts),
            ),
        )

    @staticmethod
    def _advance(
        progress: Progress | None,
        task_id: int | None,
        counts: dict[str, int],
    ) -> None:
        if progress is None or task_id is None:
            return
        progress.update(
            task_id,
            advance=1,
            counts=Sweep._counts_text(counts),
        )

    @staticmethod
    def _initial_counts() -> dict[str, int]:
        return {"ok": 0, "failure": 0, "timeout": 0, "skipped": 0}

    @staticmethod
    def _update_counts(counts: dict[str, int], case_result: _CaseResult) -> None:
        status = str(case_result.outcome.get("status", "ok"))
        counts[status] = counts.get(status, 0) + 1

    @staticmethod
    def _counts_text(counts: dict[str, int]) -> str:
        return "  ".join([
            f"[green]ok {counts.get('ok', 0)}[/green]",
            f"[red]fail {counts.get('failure', 0)}[/red]",
            f"[yellow]timeout {counts.get('timeout', 0)}[/yellow]",
            f"[cyan]skip {counts.get('skipped', 0)}[/cyan]",
        ])

    @staticmethod
    def _format_config(config: dict[str, Any], max_len: int = 48) -> str:
        text = ", ".join(f"{key}={value}" for key, value in config.items())
        return text if len(text) <= max_len else f"{text[: max_len - 3]}..."

    @staticmethod
    def _format_result(result: Any, max_len: int = 36) -> str:  # noqa: ANN401
        text = ", ".join(f"{key}={value}" for key, value in result.items()) if isinstance(result, dict) else str(result)
        return text if len(text) <= max_len else f"{text[: max_len - 3]}..."

    @staticmethod
    def _status_markup(status: str) -> str:
        styles = {
            "ok": "green",
            "failure": "red",
            "timeout": "yellow",
            "skipped": "cyan",
        }
        color = styles.get(status, "white")
        return f"[{color}]{status}[/{color}]"

    @staticmethod
    def _count_existing_rows(log_path: str) -> int:
        path = resolve_output_path(log_path, "logs")
        if not path.exists():
            return 0
        with path.open(encoding="utf-8") as handle:
            return sum(1 for _ in handle)

    def _cases(
        self,
        fn: Callable[..., R],
        benchmark_name: str,
    ) -> Iterator[_Case]:
        sig = inspect.signature(fn)
        param_names = tuple(self.params.keys())
        param_values = [list(values) for values in self.params.values()]
        if param_values:
            combinations = [dict(zip(param_names, values, strict=True)) for values in product(*param_values)]
        else:
            combinations = [{}]

        cases = [
            self._make_case(sig, benchmark_name, rep, config)
            for config in combinations
            for rep in range(1, self.repeat + 1)
        ]
        if self.shuffle:
            rng = random.Random(self.seed)  # noqa: S311
            rng.shuffle(cases)
        yield from cases

    @staticmethod
    def _make_case(
        sig: inspect.Signature,
        benchmark_name: str,
        rep: int,
        config: dict[str, Any],
    ) -> _Case:
        bound = sig.bind_partial(**config)
        bound.apply_defaults()
        log_config = dict(bound.arguments)
        log_config.pop("ctx", None)
        log_config.pop("self", None)
        log_config.pop("cls", None)
        return _Case(
            rep=rep,
            config=config,
            log_config=log_config,
            case_key=case_key(
                benchmark_name=benchmark_name,
                config=log_config,
                rep=rep,
            ),
        )
