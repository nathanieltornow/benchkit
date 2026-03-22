"""Run data classes and environment capture for BenchKit."""

from __future__ import annotations

import json
import os
import pickle  # noqa: S403
import platform
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class RunStatus(StrEnum):
    """Terminal status for one stored benchmark run."""

    OK = "ok"
    FAILURE = "failure"

    @classmethod
    def parse(cls, value: RunStatus | str) -> RunStatus:
        """Parse a status value into a ``RunStatus`` enum.

        Returns:
            RunStatus: The parsed status.
        """
        if isinstance(value, cls):
            return value
        return cls(value)


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Typed representation of one stored run."""

    benchmark: str
    sweep: str
    case_key: str
    rep: int
    status: RunStatus
    config: dict[str, Any]
    metrics: dict[str, Any]
    artifact_dir: str | None
    error_type: str | None
    error_message: str | None
    env: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class Run:
    """Typed access to one run and its artifact directory."""

    record: RunRecord

    @property
    def sweep_id(self) -> str:
        """Return the sweep identifier."""
        return self.record.sweep

    @property
    def case_key(self) -> str:
        """Return the case key hash."""
        return self.record.case_key

    @property
    def rep(self) -> int:
        """Return the repetition index."""
        return self.record.rep

    @property
    def status(self) -> RunStatus:
        """Return the run status."""
        return self.record.status

    @property
    def error_type(self) -> str | None:
        """Return the error type name, if any."""
        return self.record.error_type

    @property
    def error_message(self) -> str | None:
        """Return the error message, if any."""
        return self.record.error_message

    @property
    def config(self) -> dict[str, Any]:
        """Return a copy of the run configuration."""
        return dict(self.record.config)

    @property
    def metrics(self) -> dict[str, Any]:
        """Return a copy of the run metrics."""
        return dict(self.record.metrics)

    @property
    def run_id(self) -> str:
        """Return the run identifier."""
        return self.record.case_key

    @property
    def artifact_dir(self) -> Path:
        """Return the artifact directory path.

        Returns:
            Path: The artifact directory.

        Raises:
            FileNotFoundError: If no artifact directory is set.
        """
        if self.record.artifact_dir is None:
            msg = "Run does not have an artifact directory."
            raise FileNotFoundError(msg)
        return Path(self.record.artifact_dir)

    def path(self, name: str) -> Path:
        """Return the path to a named artifact."""
        return self.artifact_dir / name

    def exists(self, name: str) -> bool:
        """Check whether a named artifact exists.

        Returns:
            bool: True if the artifact exists.
        """
        return self.path(name).exists()

    def read_text(self, name: str, *, encoding: str = "utf-8") -> str:
        """Read a text artifact.

        Returns:
            str: The file contents.
        """
        return self.path(name).read_text(encoding=encoding)

    def read_bytes(self, name: str) -> bytes:
        """Read a binary artifact.

        Returns:
            bytes: The file contents.
        """
        return self.path(name).read_bytes()

    def load_json(self, name: str) -> Any:  # noqa: ANN401
        """Load a JSON artifact.

        Returns:
            Any: The deserialized JSON value.
        """
        return json.loads(self.read_text(name))

    def load_pickle(self, name: str) -> Any:  # noqa: ANN401
        """Load a pickle artifact.

        Returns:
            Any: The deserialized object.
        """
        with self.path(name).open("rb") as handle:
            return pickle.load(handle)  # noqa: S301


def run_from_row(row: dict[str, Any]) -> Run:
    """Construct a Run from a store query_runs() dict.

    Returns:
        Run: The constructed run object.
    """
    error = row.get("error")
    return Run(
        record=RunRecord(
            benchmark=row["benchmark"],
            sweep=row["sweep"],
            case_key=row["case_key"],
            rep=int(row.get("rep", 0)),
            status=RunStatus.parse(row["status"]),
            config=row.get("config", {}),
            metrics=row.get("metrics", {}),
            artifact_dir=row.get("artifact_dir"),
            error_type=error["type"] if isinstance(error, dict) else None,
            error_message=error["message"] if isinstance(error, dict) else None,
            env=row.get("env") or {},
            created_at=row.get("created_at", ""),
        ),
    )


def capture_env() -> dict[str, str | None]:
    """Snapshot the runtime environment for reproducibility.

    Returns:
        dict[str, str | None]: Environment metadata.
    """
    env: dict[str, str | None] = {
        "python": sys.version,
        "platform": platform.platform(),
        "arch": platform.machine(),
        "cpu_count": str(os.cpu_count()),
    }
    try:
        import git

        repo = git.Repo(search_parent_directories=True)
        env["git_sha"] = repo.head.commit.hexsha[:12]
        env["git_dirty"] = str(repo.is_dirty())
    except Exception:  # noqa: BLE001
        env["git_sha"] = None
        env["git_dirty"] = None
    return env
