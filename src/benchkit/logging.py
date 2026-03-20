"""JSONL-backed storage for benchmark runs."""

from __future__ import annotations

import datetime as dt
import json
import pickle  # noqa: S403
import platform
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import pandas as pd

from .config import resolve_output_path

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Typed representation of one finalized JSONL run row."""

    run_id: str | None
    storage_id: str | None
    sweep_id: str
    case_key: str | None
    rep: int
    status: str
    artifact_dir: str | None
    config: dict[str, Any]
    metrics: dict[str, Any]
    artifacts: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class Run:
    """Typed access to one run row and its artifact directory."""

    record: RunRecord
    row: dict[str, Any]

    @property
    def sweep_id(self) -> str:
        """Return the logical sweep id for this run."""
        return self.record.sweep_id

    @property
    def storage_id(self) -> str | None:
        """Return the internal storage id for this run when present."""
        return self.record.storage_id

    @property
    def case_key(self) -> str:
        """Return the case identity for this run."""
        return self.record.case_key or ""

    @property
    def rep(self) -> int:
        """Return the repetition index for this run."""
        return self.record.rep

    @property
    def status(self) -> str:
        """Return the terminal status for this run."""
        return self.record.status

    @property
    def config(self) -> dict[str, Any]:
        """Return the case config mapping."""
        return dict(self.record.config)

    @property
    def metrics(self) -> dict[str, Any]:
        """Return the final metrics mapping."""
        return dict(self.record.metrics)

    @property
    def artifact_dir(self) -> Path:
        """Return the artifact directory for this run.

        Raises:
            FileNotFoundError: If the run does not have a resolved artifact directory.
        """
        if self.record.artifact_dir is None:
            msg = "Run row does not include an artifact directory and no artifacts were recorded."
            raise FileNotFoundError(msg)
        return Path(self.record.artifact_dir)

    @property
    def run_id(self) -> str:
        """Return the opaque run id."""
        return self.record.run_id or ""

    def path(self, name: str) -> Path:
        """Return one file path inside the artifact directory."""
        return self.artifact_dir / name

    @property
    def artifact_paths(self) -> dict[str, Path]:
        """Return the recorded artifact paths keyed by artifact name."""
        return {
            str(record["name"]): Path(str(record["path"]))
            for record in self.record.artifacts
            if isinstance(record.get("name"), str) and isinstance(record.get("path"), str)
        }

    def exists(self, name: str) -> bool:
        """Return whether one artifact file exists."""
        return self.path(name).exists()

    def read_text(self, name: str, *, encoding: str = "utf-8") -> str:
        """Read one text artifact.

        Returns:
            str: Text content of the artifact.
        """
        return self.path(name).read_text(encoding=encoding)

    def read_bytes(self, name: str) -> bytes:
        """Read one binary artifact.

        Returns:
            bytes: Raw bytes of the artifact.
        """
        return self.path(name).read_bytes()

    def load_json(self, name: str) -> Any:  # noqa: ANN401
        """Load one JSON artifact.

        Returns:
            Any: Parsed JSON value from the artifact.
        """
        return json.loads(self.read_text(name))

    def load_pickle(self, name: str) -> Any:  # noqa: ANN401
        """Load one pickled artifact.

        Returns:
            Any: Unpickled Python value from the artifact.
        """
        with self.path(name).open("rb") as handle:
            return pickle.load(handle)  # noqa: S301

    def to_dict(self) -> dict[str, Any]:
        """Return the original JSONL row.

        Returns:
            dict[str, Any]: Raw log row for this run.
        """
        return dict(self.row)


def load_log(log_path: str | Path, *, normalize: bool = True) -> pd.DataFrame:
    """Load log entries from a JSONL log file.

    Args:
        log_path: Path to the log file.
        normalize: Whether to flatten nested dicts into columns.

    Returns:
        pd.DataFrame: DataFrame of log entries.

    Raises:
        FileNotFoundError: If the log file does not exist.
    """
    log_path = _resolve_log_path(log_path)
    if not log_path.exists():
        msg = f"Log file {log_path} does not exist."
        raise FileNotFoundError(msg)

    log_df = pd.read_json(log_path, lines=True)
    if normalize:
        log_df = pd.json_normalize(log_df.to_dict(orient="records"))
    return log_df


def load_runs(log_path: str | Path) -> list[Run]:
    """Load typed run rows from a JSONL log file.

    Returns:
        list[Run]: Parsed run rows with artifact helpers.

    Raises:
        FileNotFoundError: If the log file does not exist.
    """
    resolved = _resolve_log_path(log_path)
    if not resolved.exists():
        msg = f"Log file {resolved} does not exist."
        raise FileNotFoundError(msg)
    rows = [json.loads(line) for line in resolved.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [Run(record=_parse_run_record(row), row=row) for row in rows]


def iter_runs(log_path: str | Path) -> Iterator[Run]:
    """Iterate typed run rows from a JSONL log file.

    Returns:
        Iterator[Run]: Iterator over parsed run rows.
    """
    return iter(load_runs(log_path))


def build_run_view(
    *,
    run_id: str | None,
    sweep_id: str,
    case_key: str,
    rep: int,
    status: str,
    config: dict[str, Any],
    artifact_dir: str | Path,
    artifacts: list[dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
    row_extra: dict[str, Any] | None = None,
) -> Run:
    """Build a read-only run view from in-memory run metadata.

    Returns:
        Run: The constructed run view.
    """
    row: dict[str, Any] = {
        "run_id": run_id,
        "sweep_id": sweep_id,
        "case_key": case_key,
        "rep": rep,
        "status": status,
        "config": config,
        "result": metrics or {},
        "artifact_dir": str(artifact_dir),
        "artifacts": artifacts or [],
    }
    if row_extra is not None:
        row.update(row_extra)
    return Run(record=_parse_run_record(row), row=row)


def join_logs(
    log_paths: list[str | Path],
    *,
    how: Literal["left", "right", "outer", "inner", "cross", "left_anti", "right_anti"] = "outer",
) -> pd.DataFrame:
    """Join multiple log files on their overlapping config columns.

    Returns:
        pd.DataFrame: Merged DataFrame of log entries.

    Raises:
        ValueError: If there are no overlapping config columns between logs.
    """
    dfs = [load_log(p, normalize=True) for p in log_paths]
    if not dfs:
        return pd.DataFrame()

    merged = dfs[0]
    for df in dfs[1:]:
        config_cols = sorted(set(merged.columns).intersection(df.columns))
        config_cols = [c for c in config_cols if c.startswith("config.")]
        if not config_cols:
            msg = f"No overlapping config columns between logs:\n{merged.columns}\n---\n{df.columns}"
            raise ValueError(msg)
        merged = merged.merge(df, on=config_cols, how=how)
    return merged


def build_log_entry(
    *,
    config: dict[str, Any],
    result: Any,  # noqa: ANN401
    func_name: str,
    init_time: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable benchmark log entry.

    Returns:
        dict[str, Any]: The log row that will be written to JSONL.
    """
    entry: dict[str, Any] = {
        "config": config,
        "result": result,
        "id": str(uuid.uuid4())[:8],
        "func_name": func_name,
        "init_time": init_time,
        "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": platform.node(),
    }
    if extra is not None:
        entry.update(extra)
    return entry


def write_log_entry(
    file: Path | str,
    *,
    config: dict[str, Any],
    result: Any,  # noqa: ANN401
    func_name: str,
    init_time: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append a benchmark log entry to a JSONL target."""
    log_path = _normalize_log_target(file)
    line = (
        json.dumps(
            build_log_entry(
                config=config,
                result=result,
                func_name=func_name,
                init_time=init_time,
                extra=extra,
            ),
            default=str,
            sort_keys=True,
        )
        + "\n"
    )

    with log_path.open("a", encoding="utf-8") as f:
        f.write(line)


def _normalize_log_target(file: Path | str) -> Path:
    log_path = _resolve_log_path(file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path


def _resolve_log_path(target: str | Path) -> Path:
    candidate = Path(target)
    if candidate.suffix == ".jsonl" or candidate.is_absolute() or candidate.parent != Path():
        return resolve_output_path(candidate, "logs")
    return resolve_output_path(f"{candidate.name}.jsonl", "logs")


def _parse_run_record(row: dict[str, Any]) -> RunRecord:
    run_id = row.get("run_id")
    if not isinstance(run_id, str):
        legacy_id = row.get("id")
        run_id = legacy_id if isinstance(legacy_id, str) else None

    artifact_dir = row.get("artifact_dir")
    if not isinstance(artifact_dir, str):
        artifact_dir = None

    artifacts_value = row.get("artifacts")
    if isinstance(artifacts_value, list):
        artifacts = [item for item in artifacts_value if isinstance(item, dict)]
    else:
        artifacts = []
    if artifact_dir is None and artifacts:
        first_path = artifacts[0].get("path")
        if isinstance(first_path, str) and first_path:
            artifact_dir = str(Path(first_path).parent)

    config_value = row.get("config")
    config = dict(config_value) if isinstance(config_value, dict) else {}

    metrics_value = row.get("metrics")
    if not isinstance(metrics_value, dict):
        metrics_value = row.get("result")
    metrics = dict(metrics_value) if isinstance(metrics_value, dict) else {}

    sweep_id = row.get("sweep_id")
    if not isinstance(sweep_id, str):
        msg = "Run row is missing a valid 'sweep_id'."
        raise TypeError(msg)

    status = row.get("status")
    if not isinstance(status, str):
        msg = "Run row is missing a valid 'status'."
        raise TypeError(msg)

    rep_value = row.get("rep")
    rep = rep_value if isinstance(rep_value, int) else 1

    storage_id = row.get("storage_id")
    parsed_storage_id = storage_id if isinstance(storage_id, str) else None
    case_key = row.get("case_key")
    parsed_case_key = case_key if isinstance(case_key, str) else None

    return RunRecord(
        run_id=run_id,
        storage_id=parsed_storage_id,
        sweep_id=sweep_id,
        case_key=parsed_case_key,
        rep=rep,
        status=status,
        artifact_dir=artifact_dir,
        config=config,
        metrics=metrics,
        artifacts=artifacts,
    )
