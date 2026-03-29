"""Query helpers for stored benchmark results."""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Any

from .models import Run, RunStatus
from .store import default_store

if TYPE_CHECKING:
    from collections.abc import Mapping

    import pandas as pd


def _resolve_sweep(benchmark_id: str, sweep: str | None) -> str:
    """Resolve a sweep ID, defaulting to the latest.

    Returns:
        str: The resolved sweep ID.

    Raises:
        FileNotFoundError: If no sweep exists for the given benchmark.
    """
    resolved = sweep or default_store().latest_sweep(benchmark_id)
    if resolved is None:
        msg = f"No sweep found for benchmark {benchmark_id!r}."
        raise FileNotFoundError(msg)
    return resolved


def load_frame(
    benchmark_id: str,
    *,
    sweep: str | None = None,
    metadata: bool = False,
) -> pd.DataFrame:
    """Load benchmark results as a DataFrame.

    By default, returns only ``config.*`` and ``result.*`` columns.
    Pass ``metadata=True`` to include ``status``, ``rep``, ``case_key``,
    ``created_at``, ``artifact_dir``, and error fields.

    Returns:
        pd.DataFrame: The benchmark results.
    """
    import pandas as pd

    resolved = _resolve_sweep(benchmark_id, sweep)
    records = default_store().query_runs(benchmark=benchmark_id, sweep=resolved)
    if not records:
        return pd.DataFrame()

    rows = []
    for rec in records:
        flat: dict[str, Any] = {}
        for k, v in rec.config.items():
            flat[f"config.{k}"] = v
        for k, v in rec.metrics.items():
            flat[f"result.{k}"] = v
        if metadata:
            flat["status"] = rec.status.value
            flat["rep"] = rec.rep
            flat["case_key"] = rec.case_key
            flat["created_at"] = rec.created_at
            flat["artifact_dir"] = str(rec.artifact_dir) if rec.artifact_dir else None
            if rec.error_type is not None:
                flat["error_type"] = rec.error_type
                flat["error_message"] = rec.error_message
        rows.append(flat)
    return pd.DataFrame(rows)


def load_runs(
    benchmark_id: str,
    *,
    sweep: str | None = None,
    status: RunStatus | str | None = None,
) -> list[Run]:
    """Load typed run objects for a benchmark.

    Returns:
        list[Run]: The matching run objects.
    """
    resolved = _resolve_sweep(benchmark_id, sweep)
    status_str = RunStatus.parse(status).value if status is not None else None
    return default_store().query_runs(
        benchmark=benchmark_id,
        sweep=resolved,
        status=status_str,
    )


def get_run(
    benchmark_id: str,
    *,
    config: Mapping[str, Any],
    sweep: str | None = None,
    status: RunStatus | str | None = None,
) -> Run:
    """Return one run selected by config.

    Raises:
        FileNotFoundError: If no matching run exists.
        ValueError: If multiple matching runs exist.
    """
    target = dict(config)
    matches = [r for r in load_runs(benchmark_id, sweep=sweep, status=status) if operator.eq(r.config, target)]
    if not matches:
        msg = f"No run found for benchmark={benchmark_id!r}, config={target!r}, status={status!r}"
        raise FileNotFoundError(msg)
    if len(matches) > 1:
        msg = f"Multiple runs found for benchmark={benchmark_id!r}, config={target!r}, status={status!r}"
        raise ValueError(msg)
    return matches[0]
