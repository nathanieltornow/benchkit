"""SQLite-backed sweep state cache for resumable benchmark runs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .config import ensure_dir

if TYPE_CHECKING:
    from pathlib import Path


def default_state_path() -> Path:
    """Return the default SQLite path for sweep state."""
    return ensure_dir("state") / "sweeps.sqlite"


def state_path_for(sweep_id: str) -> Path:
    """Return the default SQLite resume cache path for one sweep id."""
    return ensure_dir("state") / f"{sweep_id}.sqlite"


def case_key(
    *,
    benchmark_name: str,
    config: dict[str, Any],
    rep: int,
) -> str:
    """Return a stable hash for one benchmark repetition."""
    payload = json.dumps(
        {"benchmark": benchmark_name, "config": config, "rep": rep},
        default=str,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(slots=True)
class SweepState:
    """Track completed sweep cases so later runs can resume."""

    path: Path = field(default_factory=default_state_path)

    def __post_init__(self) -> None:
        """Create the backing schema if needed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    case_key TEXT PRIMARY KEY,
                    benchmark_name TEXT NOT NULL,
                    rep INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    log_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def completed_keys(
        self,
        *,
        benchmark_name: str,
        log_path: str,
    ) -> set[str]:
        """Return the cache keys for previously successful cases."""
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT case_key
                FROM cases
                WHERE benchmark_name = ?
                  AND log_path = ?
                  AND status = 'ok'
                """,
                (benchmark_name, log_path),
            ).fetchall()
        return {row[0] for row in rows}

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
        """Insert or update the cached state for one case."""
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO cases (
                    case_key,
                    benchmark_name,
                    rep,
                    status,
                    config_json,
                    log_path,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_key) DO UPDATE SET
                    status=excluded.status,
                    config_json=excluded.config_json,
                    log_path=excluded.log_path,
                    updated_at=excluded.updated_at
                """,
                (
                    case_key,
                    benchmark_name,
                    rep,
                    status,
                    json.dumps(config, default=str, sort_keys=True),
                    log_path,
                    updated_at,
                ),
            )

    def clear_cases(self, *, benchmark_name: str, log_path: str) -> None:
        """Remove cached state for one benchmark/log pair."""
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "DELETE FROM cases WHERE benchmark_name = ? AND log_path = ?",
                (benchmark_name, log_path),
            )
