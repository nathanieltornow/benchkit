"""Analysis helpers for stored benchmark sweeps."""

from __future__ import annotations

import json
import operator
import pickle  # noqa: S403
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from matplotlib.figure import Figure

from .config import benchkit_home
from .logging import Run, RunStatus, run_from_row
from .store import default_store

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

    import pandas as pd


def _validate_name(name: str, *, what: str) -> str:
    path = Path(name)
    if path.is_absolute() or path.parent != Path():
        msg = f"{what} names must be simple file names, not paths."
        raise ValueError(msg)
    return path.name


@dataclass(frozen=True, slots=True)
class Analysis:
    """Read-only handle to one stored benchmark sweep."""

    id: str
    sweep: str

    @property
    def sweep_id(self) -> str:
        """Return the sweep identifier."""
        return self.sweep

    @property
    def _analysis_root(self) -> Path:
        root = benchkit_home() / "analysis" / self.id / self.sweep
        root.mkdir(parents=True, exist_ok=True)
        return root

    @property
    def _data_dir(self) -> Path:
        d = self._analysis_root / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def _figures_dir(self) -> Path:
        d = self._analysis_root / "figures"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def load_frame(self, *, normalize: bool = True) -> pd.DataFrame:
        """Load benchmark results into a DataFrame.

        Returns:
            pd.DataFrame: The benchmark results.
        """
        import pandas as pd

        rows = default_store().query_runs(benchmark=self.id, sweep=self.sweep)
        if not rows:
            return pd.DataFrame()
        if not normalize:
            return pd.DataFrame(rows)

        records = []
        for row in rows:
            flat: dict[str, Any] = {}
            for k, v in row.get("config", {}).items():
                flat[f"config.{k}"] = v
            for k, v in row.get("metrics", {}).items():
                flat[f"result.{k}"] = v
            flat["status"] = row["status"]
            flat["case_key"] = row["case_key"]
            flat["created_at"] = row.get("created_at")
            flat["artifact_dir"] = row.get("artifact_dir")
            error = row.get("error")
            if isinstance(error, dict):
                flat["error_type"] = error.get("type")
                flat["error_message"] = error.get("message")
            records.append(flat)
        return pd.DataFrame(records)

    def load_runs(self, *, status: RunStatus | str | None = None) -> list[Run]:
        """Load typed run objects for this sweep.

        Returns:
            list[Run]: The matching run objects.
        """
        status_str = RunStatus.parse(status).value if status is not None else None
        rows = default_store().query_runs(
            benchmark=self.id,
            sweep=self.sweep,
            status=status_str,
        )
        return [run_from_row(row) for row in rows]

    def summary(self) -> dict[str, int]:
        """Return a count of runs by status.

        Returns:
            dict[str, int]: Mapping of status to count (e.g. ``{"ok": 5, "failure": 1}``).
        """
        rows = default_store().query_runs(benchmark=self.id, sweep=self.sweep)
        counts: dict[str, int] = {}
        for row in rows:
            s = row["status"]
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

    def save_dataframe(self, df: pd.DataFrame, name: str, *, file_format: str = "parquet") -> Path:
        """Save an analysis dataframe.

        Returns:
            Path: The path to the saved file.

        Raises:
            ValueError: If the file format is not supported.
        """
        if file_format not in {"parquet", "csv"}:
            msg = f"Unsupported format {file_format!r}. Use 'parquet' or 'csv'."
            raise ValueError(msg)
        suffix = ".parquet" if file_format == "parquet" else ".csv"
        target = self._data_dir / f"{Path(_validate_name(name, what='Dataframe')).stem}{suffix}"
        if file_format == "parquet":
            df.to_parquet(target, index=False)
        else:
            df.to_csv(target, index=False)
        return target

    def save_json(self, name: str, value: Any) -> Path:  # noqa: ANN401
        """Save a JSON artifact.

        Returns:
            Path: The path to the saved file.
        """
        target = self._data_dir / _validate_name(name, what="JSON artifact")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, default=str, sort_keys=True, indent=2), encoding="utf-8")
        return target

    def save_pickle(self, name: str, value: Any) -> Path:  # noqa: ANN401
        """Save a pickle artifact.

        Returns:
            Path: The path to the saved file.
        """
        target = self._data_dir / _validate_name(name, what="Pickle artifact")
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
        """Save figure outputs inside the analysis tree.

        Returns:
            list[Path]: Paths to saved figure files.
        """
        _validate_name(plot_name, what="Plot")
        selected_extensions = extensions or ["pdf", "png"]
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d-%H-%M")
        out_dir = self._figures_dir / plot_name / timestamp
        out_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []

        def save_one(fig: object, filename: str) -> None:
            if not isinstance(fig, Figure):
                return
            output_path = out_dir / filename
            fig.tight_layout()
            fig.savefig(output_path, dpi=400, bbox_inches="tight")
            saved.append(output_path)

        if isinstance(figs, Figure):
            for ext in selected_extensions:
                save_one(figs, f"{plot_name}.{ext}")
        else:
            for idx, fig in enumerate(figs):
                for ext in selected_extensions:
                    save_one(fig, f"{plot_name}_{idx}.{ext}")

        return saved


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
