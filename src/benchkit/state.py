"""Compatibility wrapper for BenchKit resume state."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .store import BenchkitStore, store_path

if TYPE_CHECKING:
    from pathlib import Path


def default_state_path() -> Path:
    """Return the central SQLite path for benchmark resume state."""
    return store_path()


def state_path_for(_: str) -> Path:
    """Return the central SQLite path for benchmark resume state."""
    return store_path()


def case_key(*, benchmark_name: str, config: dict[str, Any], rep: int) -> str:
    """Return a stable hash for one benchmark repetition."""
    payload = json.dumps(
        {"benchmark": benchmark_name, "config": config, "rep": rep},
        default=str,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(slots=True)
class SweepState:
    """Compatibility wrapper around the central store's resume-case helpers."""

    path: Path = field(default_factory=default_state_path)

    def completed_keys(self, *, benchmark_name: str, log_path: str) -> set[str]:
        """Return the keys of previously successful cases for one log."""
        return BenchkitStore(self.path).completed_resume_keys(
            benchmark_name=benchmark_name,
            log_path=log_path,
        )

    def sync_from_log(self, *, benchmark_name: str, log_path: str) -> None:
        """Rebuild cached case state from the canonical JSONL log."""
        BenchkitStore(self.path).sync_resume_cases_from_log(
            benchmark_name=benchmark_name,
            log_path=log_path,
        )

    def record_case(
        self,
        *,
        case_key: str,
        benchmark_name: str,
        rep: int,
        status: str,
        config: dict[str, Any],
        log_path: str,
        updated_at: str,
    ) -> None:
        """Insert or update one cached case row."""
        BenchkitStore(self.path).record_resume_case(
            case_key=case_key,
            benchmark_name=benchmark_name,
            rep=rep,
            status=status,
            config=config,
            log_path=log_path,
            updated_at=updated_at,
        )

    def clear_cases(self, *, benchmark_name: str, log_path: str) -> None:
        """Remove cached state for one benchmark/log pair."""
        BenchkitStore(self.path).clear_resume_cases(
            benchmark_name=benchmark_name,
            log_path=log_path,
        )
