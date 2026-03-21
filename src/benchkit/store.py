"""Single-table SQLite storage for BenchKit runs."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .config import benchkit_home

if TYPE_CHECKING:
    from pathlib import Path


def store_path() -> Path:
    """Return the central BenchKit SQLite database path.

    Returns:
        Path: The database file path.
    """
    root = benchkit_home()
    root.mkdir(parents=True, exist_ok=True)
    return root / "benchmarks.sqlite"


def case_key(*, benchmark_name: str, config: dict[str, Any]) -> str:
    """Return a stable hash for one benchmark case.

    Returns:
        str: The hex digest case key.
    """
    payload = json.dumps(
        {"benchmark": benchmark_name, "config": config},
        default=str,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(slots=True)
class BenchkitStore:
    """Single-table SQLite store for benchmark runs."""

    path: Path = field(default_factory=store_path)

    def __post_init__(self) -> None:
        """Ensure the schema exists."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    benchmark TEXT NOT NULL,
                    sweep TEXT NOT NULL,
                    case_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    artifact_dir TEXT,
                    error TEXT,
                    env TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (benchmark, sweep, case_key)
                )
                """,
            )

    def _connect(self) -> sqlite3.Connection:
        """Open a connection to the store.

        Returns:
            sqlite3.Connection: The database connection.
        """
        return sqlite3.connect(self.path, timeout=30)

    def insert_run(
        self,
        *,
        benchmark: str,
        sweep: str,
        case_key: str,
        status: str,
        config: dict[str, Any],
        metrics: dict[str, Any],
        artifact_dir: str | None = None,
        error: dict[str, str] | None = None,
        env: dict[str, Any] | None = None,
    ) -> None:
        """Insert or replace one run row."""
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs
                    (benchmark, sweep, case_key, status, config, metrics,
                     artifact_dir, error, env, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    benchmark,
                    sweep,
                    case_key,
                    status,
                    json.dumps(config, default=str, sort_keys=True),
                    json.dumps(metrics, default=str, sort_keys=True),
                    artifact_dir,
                    json.dumps(error, sort_keys=True) if error else None,
                    json.dumps(env, default=str, sort_keys=True) if env else None,
                    now,
                ),
            )

    def completed_keys(self, *, benchmark: str, sweep: str) -> set[str]:
        """Return case keys that completed successfully.

        Returns:
            set[str]: The set of completed case keys.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT case_key FROM runs WHERE benchmark = ? AND sweep = ? AND status = 'ok'",
                (benchmark, sweep),
            ).fetchall()
        return {row[0] for row in rows}

    def latest_sweep(self, benchmark: str) -> str | None:
        """Return the most recent sweep ID for a benchmark.

        Returns:
            str | None: The latest sweep ID, or None if no sweeps exist.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(sweep) FROM runs WHERE benchmark = ?",
                (benchmark,),
            ).fetchone()
        return row[0] if row and row[0] is not None else None

    def query_runs(
        self,
        *,
        benchmark: str,
        sweep: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query run rows with JSON fields parsed.

        Returns:
            list[dict[str, Any]]: The matching run rows.
        """
        query = "SELECT * FROM runs WHERE benchmark = ? AND sweep = ?"
        params: list[Any] = [benchmark, sweep]
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at ASC"
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [self._parse_row(dict(row)) for row in rows]

    def list_sweeps(self, benchmark: str | None = None) -> list[dict[str, Any]]:
        """List distinct sweeps with counts.

        Returns:
            list[dict[str, Any]]: The sweep summary rows.
        """
        query = """
            SELECT benchmark, sweep, MIN(created_at) as created_at, COUNT(*) as count
            FROM runs
        """
        params: list[Any] = []
        if benchmark is not None:
            query += " WHERE benchmark = ?"
            params.append(benchmark)
        query += " GROUP BY benchmark, sweep ORDER BY benchmark, sweep DESC"
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def artifact_dir_for(*, benchmark: str, sweep: str, case_key: str) -> Path:
        """Return the canonical artifact directory for one run.

        Returns:
            Path: The artifact directory path.
        """
        path = benchkit_home() / "runs" / benchmark / sweep / case_key[:16]
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _parse_row(row: dict[str, Any]) -> dict[str, Any]:
        """Parse JSON columns in a raw DB row.

        Returns:
            dict[str, Any]: The row with parsed JSON fields.
        """
        for col in ("config", "metrics"):
            if isinstance(row.get(col), str):
                row[col] = json.loads(row[col])
        for col in ("error", "env"):
            val = row.get(col)
            if isinstance(val, str):
                row[col] = json.loads(val)
            elif val is None:
                row[col] = None
        return row


_DEFAULT_STORE: BenchkitStore | None = None


def default_store() -> BenchkitStore:
    """Return the cached default BenchKit store instance.

    Returns:
        BenchkitStore: The singleton store.
    """
    global _DEFAULT_STORE  # noqa: PLW0603
    if _DEFAULT_STORE is None or _DEFAULT_STORE.path != store_path():
        _DEFAULT_STORE = BenchkitStore()
    return _DEFAULT_STORE
