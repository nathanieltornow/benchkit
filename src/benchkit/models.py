"""Data models for BenchKit runs, sweeps, and environment capture."""

from __future__ import annotations

import json
import os
import pickle  # noqa: S403
import platform
import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


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
class Run:
    """One stored benchmark run with typed access to fields and artifacts."""

    benchmark: str
    sweep: str
    case_key: str
    rep: int
    status: RunStatus
    config: dict[str, Any]
    metrics: dict[str, Any]
    artifact_dir: Path | None
    error_type: str | None
    error_message: str | None
    env: dict[str, Any]
    created_at: str

    @property
    def sweep_id(self) -> str:
        """Return the sweep identifier."""
        return self.sweep

    @property
    def run_id(self) -> str:
        """Return the run identifier."""
        return self.case_key

    # -- artifact helpers --------------------------------------------------

    def path(self, name: str) -> Path:
        """Return the path to a named artifact.

        Raises:
            FileNotFoundError: If no artifact directory is set.
        """
        if self.artifact_dir is None:
            msg = "Run does not have an artifact directory."
            raise FileNotFoundError(msg)
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


@dataclass(frozen=True, slots=True)
class SweepSummary:
    """Summary of one stored sweep."""

    benchmark: str
    sweep: str
    created_at: str
    count: int


def capture_env() -> dict[str, str]:
    """Snapshot the runtime environment for reproducibility.

    Returns:
        dict[str, str]: Environment metadata.
    """
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "arch": platform.machine(),
        "cpu_count": str(os.cpu_count()),
    }
