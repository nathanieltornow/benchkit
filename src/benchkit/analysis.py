"""Analysis helpers for stored benchmark sweeps."""

from __future__ import annotations

import json
import pickle  # noqa: S403
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .artifacts import ArtifactIndex
from .config import benchkit_home, resolve_output_path
from .logging import Run, iter_runs, load_log, load_runs
from .plot import save_figure
from .state import SweepState
from .store import BenchkitStore

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

    import pandas as pd
    from matplotlib.figure import Figure


def _matches_run_config(run_config: dict[str, Any], target_config: dict[str, Any]) -> bool:
    """Match either the exact logged config or the inner benchmark case payload.

    Returns:
        bool: Whether the run config matches the requested config.
    """
    if run_config == target_config:
        return True
    inner_case = run_config.get("case")
    return isinstance(inner_case, dict) and inner_case == target_config


@dataclass(frozen=True, slots=True)
class AnalysisPaths:
    """Resolved output paths for one benchmark analysis tree."""

    root: Path
    data_dir: Path
    figures_dir: Path
    sweep_dir: Path
    log_path: Path

    @classmethod
    def for_analysis(
        cls,
        benchmark_key: str,
        *,
        analysis_root: str | Path | None = None,
        log_path: str | Path | None = None,
    ) -> AnalysisPaths:
        """Build the canonical path layout for one benchmark storage id.

        Returns:
            AnalysisPaths: Resolved analysis, data, figure, and log paths.

        Raises:
            ValueError: If the benchmark key does not include a sweep id.
        """
        base_root = (
            resolve_output_path(analysis_root, "analysis")
            if analysis_root is not None
            else benchkit_home() / "analysis"
        )
        if "--" not in benchmark_key:
            msg = f"Expected storage id '<benchmark-id>--<sweep-id>', got {benchmark_key!r}."
            raise ValueError(msg)
        benchmark_id, sweep_id = benchmark_key.split("--", 1)
        sweep_dir = BenchkitStore().sweep_dir(benchmark_id=benchmark_id, sweep_id=sweep_id)
        root = base_root / benchmark_key
        data_dir = root / "data"
        figures_dir = root / "figures"
        resolved_log_path = Path(log_path) if log_path is not None else sweep_dir / "log.jsonl"
        for path in (root, data_dir, figures_dir):
            path.mkdir(parents=True, exist_ok=True)
        return cls(
            root=root,
            data_dir=data_dir,
            figures_dir=figures_dir,
            sweep_dir=sweep_dir,
            log_path=resolved_log_path,
        )


@dataclass(frozen=True, slots=True)
class Analysis:
    """Read-only handle to one stored benchmark sweep."""

    id: str
    sweep: str | None = None
    log_path: str | Path | None = None
    analysis_root: str | Path | None = None

    @property
    def sweep_id(self) -> str:
        """Return the logical sweep id for this benchmark analysis."""
        return self.id if self.sweep is None else self.sweep

    @property
    def storage_id(self) -> str:
        """Return the physical storage id for this benchmark and sweep."""
        return self.id if self.sweep is None else f"{self.id}--{self.sweep}"

    @property
    def paths(self) -> AnalysisPaths:
        """Return the resolved output paths for this benchmark sweep."""
        return AnalysisPaths.for_analysis(
            self.storage_id,
            analysis_root=self.analysis_root,
            log_path=self.log_path,
        )

    def sync_cache(self) -> None:
        """Repair disposable caches from the JSONL log."""
        log_path = str(self.paths.log_path)
        SweepState().sync_from_log(
            benchmark_name=self.storage_id,
            log_path=log_path,
        )
        ArtifactIndex().sync_from_log(
            sweep_id=self.sweep_id,
            log_path=log_path,
        )

    def load_frame(self, *, normalize: bool = True) -> pd.DataFrame:
        """Load the benchmark log into a dataframe.

        Returns:
            pd.DataFrame: The loaded log rows.
        """
        return load_log(self.paths.log_path, normalize=normalize)

    def load_runs(self, *, status: str | None = None) -> list[Run]:
        """Load typed run rows for this benchmark sweep.

        Returns:
            list[Run]: Stored runs, optionally filtered by status.
        """
        runs = load_runs(self.paths.log_path)
        if status is None:
            return runs
        return [run for run in runs if run.status == status]

    def __iter__(self) -> Iterator[Run]:
        """Iterate over all runs in this analysis view.

        Returns:
            Iterator[Run]: Iterator over stored runs.
        """
        return iter(self.load_runs())

    def iter_runs(self, *, status: str | None = None) -> Iterator[Run]:
        """Iterate typed run rows for this benchmark sweep.

        Returns:
            Iterator[Run]: Iterator over stored runs, optionally filtered by status.
        """
        runs = iter_runs(self.paths.log_path)
        if status is None:
            return runs
        return (run for run in runs if run.status == status)

    def get_run(
        self,
        *,
        config: Mapping[str, Any],
        rep: int,
        status: str | None = None,
    ) -> Run:
        """Return one run selected by config and repetition.

        Returns:
            Run: The selected stored run.

        Raises:
            FileNotFoundError: If no matching run exists.
            ValueError: If multiple matching runs exist.
        """
        target_config = dict(config)
        matches = [
            run
            for run in self.load_runs(status=status)
            if run.rep == rep and _matches_run_config(run.config, target_config)
        ]
        if not matches:
            msg = f"No run found for benchmark={self.id!r}, config={target_config!r}, rep={rep}, status={status!r}"
            raise FileNotFoundError(msg)
        if len(matches) > 1:
            msg = (
                f"Multiple runs found for benchmark={self.id!r}, config={target_config!r}, rep={rep}, status={status!r}"
            )
            raise ValueError(msg)
        return matches[0]

    def save_dataframe(self, df: pd.DataFrame, name: str, *, file_format: str = "parquet") -> Path:
        """Save an analysis dataframe under the benchmark data directory.

        Returns:
            Path: The saved dataframe path.

        Raises:
            ValueError: If the requested file format is unsupported.
        """
        if file_format not in {"parquet", "csv"}:
            msg = f"Unsupported dataframe format {file_format!r}. Use 'parquet' or 'csv'."
            raise ValueError(msg)
        suffix = ".parquet" if file_format == "parquet" else ".csv"
        target = self.paths.data_dir / f"{Path(name).stem}{suffix}"
        if file_format == "parquet":
            df.to_parquet(target, index=False)
        else:
            df.to_csv(target, index=False)
        return target

    def save_json(self, name: str, value: Any) -> Path:  # noqa: ANN401
        """Save one JSON analysis artifact under the benchmark data directory.

        Returns:
            Path: The saved JSON path.
        """
        target = self.paths.data_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, default=str, sort_keys=True, indent=2), encoding="utf-8")
        return target

    def save_pickle(self, name: str, value: Any) -> Path:  # noqa: ANN401
        """Save one Python object under the benchmark data directory.

        Returns:
            Path: The saved pickle path.
        """
        target = self.paths.data_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            pickle.dump(value, handle)
        return target

    def save_figure(
        self,
        figs: Figure | Iterable[Figure],
        *,
        plot_name: str,
        extensions: list[str] | None = None,
    ) -> list[Path]:
        """Save figure outputs inside the benchmark analysis tree.

        Returns:
            list[Path]: Saved figure paths.
        """
        return save_figure(
            figs,
            plot_name=plot_name,
            dir_path=self.paths.figures_dir,
            extensions=extensions or ["pdf", "png"],
        )


def open_analysis(
    study_id: str,
    *,
    sweep: str | None = None,
    analysis_root: str | Path | None = None,
    log_path: str | Path | None = None,
    sync_cache: bool = True,
) -> Analysis:
    """Open stored benchmark results for analysis and plotting.

    Returns:
        Analysis: The reopened analysis handle.
    """
    resolved_sweep = sweep or BenchkitStore().resolve_sweep(study_id)
    opened = Analysis(
        id=study_id,
        sweep=resolved_sweep,
        log_path=log_path,
        analysis_root=analysis_root,
    )
    if sync_cache:
        opened.sync_cache()
    return opened
