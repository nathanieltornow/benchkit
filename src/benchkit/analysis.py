"""Analysis helpers for stored benchmark sweeps."""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .models import Run, RunStatus
from .store import default_store

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    import pandas as pd


@dataclass(frozen=True, slots=True)
class Analysis:
    """Read-only handle to one stored benchmark sweep."""

    id: str
    sweep: str

    @property
    def sweep_id(self) -> str:
        """Return the sweep identifier."""
        return self.sweep

    def load_frame(self) -> pd.DataFrame:
        """Load benchmark results into a normalized DataFrame.

        Columns are ``config.*``, ``result.*``, plus ``status``, ``rep``,
        ``case_key``, ``created_at``, ``artifact_dir``, and optional error
        fields.

        Returns:
            pd.DataFrame: The benchmark results.
        """
        import pandas as pd

        records = default_store().query_runs(benchmark=self.id, sweep=self.sweep)
        if not records:
            return pd.DataFrame()

        rows = []
        for rec in records:
            flat: dict[str, Any] = {}
            for k, v in rec.config.items():
                flat[f"config.{k}"] = v
            for k, v in rec.metrics.items():
                flat[f"result.{k}"] = v
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

    def load_runs(self, *, status: RunStatus | str | None = None) -> list[Run]:
        """Load typed run objects for this sweep.

        Returns:
            list[Run]: The matching run objects.
        """
        status_str = RunStatus.parse(status).value if status is not None else None
        return default_store().query_runs(
            benchmark=self.id,
            sweep=self.sweep,
            status=status_str,
        )

    def summary(self) -> dict[str, int]:
        """Return a count of runs by status.

        Returns:
            dict[str, int]: Mapping of status to count (e.g. ``{"ok": 5, "failure": 1}``).
        """
        records = default_store().query_runs(benchmark=self.id, sweep=self.sweep)
        counts: dict[str, int] = {}
        for rec in records:
            s = rec.status.value
            counts[s] = counts.get(s, 0) + 1
        return counts

    def is_complete(self, expected: int) -> bool:
        """Check whether the sweep has the expected number of successful runs.

        Args:
            expected: The number of cases that should have completed successfully.

        Returns:
            bool: True if the number of OK runs matches expected.
        """
        counts = self.summary()
        return counts.get("ok", 0) >= expected

    def __iter__(self) -> Iterator[Run]:
        """Iterate over all runs in this sweep.

        Returns:
            Iterator[Run]: Iterator over the runs.
        """
        return iter(self.load_runs())

    def get_run(
        self,
        *,
        config: Mapping[str, Any],
        status: RunStatus | str | None = None,
    ) -> Run:
        """Return one run selected by config.

        Raises:
            FileNotFoundError: If no matching run exists.
            ValueError: If multiple matching runs exist.
        """
        target = dict(config)
        matches = [run for run in self.load_runs(status=status) if operator.eq(run.config, target)]
        if not matches:
            msg = f"No run found for benchmark={self.id!r}, config={target!r}, status={status!r}"
            raise FileNotFoundError(msg)
        if len(matches) > 1:
            msg = f"Multiple runs found for benchmark={self.id!r}, config={target!r}, status={status!r}"
            raise ValueError(msg)
        return matches[0]


def open_analysis(
    study_id: str,
    *,
    sweep: str | None = None,
) -> Analysis:
    """Open stored benchmark results for analysis.

    Returns:
        Analysis: Handle to the stored sweep.

    Raises:
        FileNotFoundError: If no sweep exists for the given benchmark.
    """
    resolved = sweep or default_store().latest_sweep(study_id)
    if resolved is None:
        msg = f"No sweep found for benchmark {study_id!r}."
        raise FileNotFoundError(msg)
    return Analysis(id=study_id, sweep=resolved)


def load_frame(benchmark_id: str, *, sweep: str | None = None) -> pd.DataFrame:
    """Load benchmark results as a DataFrame.

    Convenience wrapper around ``open_analysis(...).load_frame()``.

    Returns:
        pd.DataFrame: The benchmark results.
    """
    return open_analysis(benchmark_id, sweep=sweep).load_frame()


def load_runs(
    benchmark_id: str,
    *,
    sweep: str | None = None,
    status: RunStatus | str | None = None,
) -> list[Run]:
    """Load typed run objects for a benchmark.

    Convenience wrapper around ``open_analysis(...).load_runs()``.

    Returns:
        list[Run]: The matching run objects.
    """
    return open_analysis(benchmark_id, sweep=sweep).load_runs(status=status)
