"""Central storage layer for BenchKit metadata and indexes."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import benchkit_home, resolve_output_path

if TYPE_CHECKING:
    from collections.abc import Iterable


def store_path() -> Path:
    """Return the central BenchKit SQLite database path."""
    root = benchkit_home()
    root.mkdir(parents=True, exist_ok=True)
    return root / "benchmarks.sqlite"


def execution_log_path() -> Path:
    """Return the global execution event log path."""
    root = benchkit_home()
    root.mkdir(parents=True, exist_ok=True)
    return root / "executions.jsonl"


@dataclass(frozen=True, slots=True)
class SweepRecord:
    """One benchmark sweep row from the central store."""

    benchmark_id: str
    sweep_id: str
    source_path: str
    is_current: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class IndexedRun:
    """One indexed benchmark run row from the central store."""

    run_id: str
    benchmark_id: str
    sweep_id: str
    storage_id: str
    rep: int
    status: str
    config: dict[str, Any]
    metrics: dict[str, Any]
    run_path: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class IndexedArtifact:
    """One indexed artifact row from the central store."""

    sweep_id: str
    case_key: str
    rep: int
    attempt: int
    name: str
    path: str
    kind: str
    size_bytes: int
    config: dict[str, Any]
    created_at: str


def _config_json(config: dict[str, Any]) -> str:
    return json.dumps(config, default=str, sort_keys=True)


@dataclass(slots=True)
class BenchkitStore:
    """Single entrypoint for BenchKit database-backed metadata and indexes."""

    path: Path = field(default_factory=store_path)

    def __post_init__(self) -> None:
        """Ensure the central SQLite schema exists."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sweeps (
                    benchmark_id TEXT NOT NULL,
                    sweep_id TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    is_current INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (benchmark_id, sweep_id)
                )
                """,
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    benchmark_id TEXT NOT NULL,
                    sweep_id TEXT NOT NULL,
                    storage_id TEXT NOT NULL,
                    rep INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    run_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    sweep_id TEXT NOT NULL,
                    case_key TEXT NOT NULL,
                    rep INTEGER NOT NULL,
                    attempt INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    config_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (sweep_id, case_key, rep, attempt, name, path)
                )
                """,
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS resume_cases (
                    case_key TEXT PRIMARY KEY,
                    benchmark_name TEXT NOT NULL,
                    rep INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    log_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
            )

    def connect(self) -> sqlite3.Connection:
        """Open a connection to the central BenchKit database.

        Returns:
            sqlite3.Connection: Open SQLite connection for BenchKit metadata.
        """
        return sqlite3.connect(self.path)

    def run_dir(self, *, benchmark_id: str, sweep_id: str, run_id: str) -> Path:
        """Return the canonical directory for one stored run."""
        path = self.sweep_dir(benchmark_id=benchmark_id, sweep_id=sweep_id) / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def sweep_dir(*, benchmark_id: str, sweep_id: str) -> Path:
        """Return the canonical directory for one benchmark sweep."""
        path = benchkit_home() / "runs" / benchmark_id / sweep_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def log_path(
        self,
        storage_id: str | Path | None = None,
        *,
        benchmark_id: str | None = None,
        sweep_id: str | None = None,
    ) -> Path:
        """Return the canonical JSONL log path for one benchmark sweep.

        Raises:
            ValueError: If neither a storage id nor an explicit benchmark/sweep pair is provided.
        """
        if benchmark_id is not None and sweep_id is not None:
            return self.sweep_dir(benchmark_id=benchmark_id, sweep_id=sweep_id) / "log.jsonl"
        if storage_id is None:
            msg = "Either storage_id or benchmark_id and sweep_id must be provided."
            raise ValueError(msg)
        return resolve_output_path(storage_id, "logs")

    def count_log_rows(self, log_path: str | Path) -> int:
        """Return the number of JSONL rows already present in a log."""
        path = self.log_path(log_path)
        if not path.exists():
            return 0
        with path.open(encoding="utf-8") as handle:
            return sum(1 for _ in handle)

    def append_log_entry(
        self,
        *,
        log_path: str | Path,
        config: dict[str, Any],
        result: Any,  # noqa: ANN401
        func_name: str,
        init_time: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Append one canonical run row to a benchmark log."""
        from .logging import build_log_entry

        path = self.log_path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
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
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def create_sweep(self, *, benchmark_id: str, source_path: str) -> str:
        """Create and select a new sweep for one benchmark.

        Returns:
            str: The new sweep id.
        """
        timestamp = dt.datetime.now(dt.timezone.utc)
        now = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        sweep_id = timestamp.strftime("%Y%m%dT%H%M%S%fZ")
        with self.connect() as conn:
            conn.execute("UPDATE sweeps SET is_current = 0 WHERE benchmark_id = ?", (benchmark_id,))
            conn.execute(
                """
                INSERT INTO sweeps (benchmark_id, sweep_id, source_path, is_current, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (benchmark_id, sweep_id, source_path, now, now),
            )
        return sweep_id

    def current_sweep(self, benchmark_id: str) -> str | None:
        """Return the current sweep id for one benchmark, if any."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT sweep_id FROM sweeps WHERE benchmark_id = ? AND is_current = 1",
                (benchmark_id,),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def latest_sweep(self, benchmark_id: str) -> str | None:
        """Return the newest registered sweep id for one benchmark, if any."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT sweep_id
                FROM sweeps
                WHERE benchmark_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (benchmark_id,),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def resolve_sweep(self, benchmark_id: str) -> str | None:
        """Return the current sweep when available, else the newest stored sweep."""
        return self.current_sweep(benchmark_id) or self.latest_sweep(benchmark_id)

    def set_current_sweep(self, *, benchmark_id: str, sweep_id: str) -> None:
        """Mark one sweep as the current append target."""
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.connect() as conn:
            conn.execute("UPDATE sweeps SET is_current = 0 WHERE benchmark_id = ?", (benchmark_id,))
            conn.execute(
                "UPDATE sweeps SET is_current = 1, updated_at = ? WHERE benchmark_id = ? AND sweep_id = ?",
                (now, benchmark_id, sweep_id),
            )

    def list_sweeps(self, benchmark_id: str | None = None) -> list[SweepRecord]:
        """List registered sweeps.

        Returns:
            list[SweepRecord]: Stored sweep rows.
        """
        query = """
            SELECT benchmark_id, sweep_id, source_path, is_current, created_at, updated_at
            FROM sweeps
        """
        params: list[Any] = []
        if benchmark_id is not None:
            query += " WHERE benchmark_id = ?"
            params.append(benchmark_id)
        query += " ORDER BY benchmark_id, created_at DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            SweepRecord(
                benchmark_id=str(row[0]),
                sweep_id=str(row[1]),
                source_path=str(row[2]),
                is_current=bool(row[3]),
                created_at=str(row[4]),
                updated_at=str(row[5]),
            )
            for row in rows
        ]

    def index_runs(
        self,
        *,
        benchmark_id: str,
        sweep_id: str,
        storage_id: str,
        runs: Iterable[Any],
    ) -> None:
        """Upsert run rows from one completed analysis result set."""
        updated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = [
            (
                str(run.run_id),
                benchmark_id,
                sweep_id,
                storage_id,
                int(run.rep),
                str(run.status),
                _config_json(run.config),
                _config_json(run.metrics),
                str(run.row.get("artifact_dir", "")),
                updated_at,
            )
            for run in runs
        ]
        if not rows:
            return
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO runs (
                    run_id,
                    benchmark_id,
                    sweep_id,
                    storage_id,
                    rep,
                    status,
                    config_json,
                    metrics_json,
                    run_path,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    benchmark_id = excluded.benchmark_id,
                    sweep_id = excluded.sweep_id,
                    storage_id = excluded.storage_id,
                    rep = excluded.rep,
                    status = excluded.status,
                    config_json = excluded.config_json,
                    metrics_json = excluded.metrics_json,
                    run_path = excluded.run_path,
                    updated_at = excluded.updated_at
                """,
                rows,
            )

    def list_runs(
        self,
        *,
        benchmark_id: str,
        sweep_id: str | None = None,
        status: str | None = None,
    ) -> list[IndexedRun]:
        """List indexed runs from the central store.

        Returns:
            list[IndexedRun]: Indexed run rows.
        """
        query = """
            SELECT
                run_id,
                benchmark_id,
                sweep_id,
                storage_id,
                rep,
                status,
                config_json,
                metrics_json,
                run_path,
                updated_at
            FROM runs
            WHERE benchmark_id = ?
        """
        params: list[Any] = [benchmark_id]
        if sweep_id is not None:
            query += " AND sweep_id = ?"
            params.append(sweep_id)
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY sweep_id DESC, rep ASC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            IndexedRun(
                run_id=str(row[0]),
                benchmark_id=str(row[1]),
                sweep_id=str(row[2]),
                storage_id=str(row[3]),
                rep=int(row[4]),
                status=str(row[5]),
                config=json.loads(row[6]),
                metrics=json.loads(row[7]),
                run_path=str(row[8]),
                updated_at=str(row[9]),
            )
            for row in rows
        ]

    def record_artifacts(
        self,
        *,
        sweep_id: str,
        case_key: str,
        rep: int,
        attempt: int,
        config: dict[str, Any],
        artifacts: list[dict[str, Any]],
    ) -> None:
        """Insert artifact rows for one case attempt."""
        if not artifacts:
            return
        created_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        config_json = _config_json(config)
        rows = [
            (
                sweep_id,
                case_key,
                rep,
                attempt,
                str(artifact["name"]),
                str(artifact["path"]),
                str(artifact.get("kind", "file")),
                int(artifact.get("size_bytes", 0)),
                config_json,
                created_at,
            )
            for artifact in artifacts
        ]
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO artifacts (
                    sweep_id,
                    case_key,
                    rep,
                    attempt,
                    name,
                    path,
                    kind,
                    size_bytes,
                    config_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def list_artifacts(
        self,
        sweep_id: str,
        *,
        config: dict[str, Any] | None = None,
        rep: int | None = None,
        name: str | None = None,
    ) -> list[IndexedArtifact]:
        """Return indexed artifacts matching the provided selector."""
        query = """
            SELECT sweep_id, case_key, rep, attempt, name, path, kind, size_bytes, config_json, created_at
            FROM artifacts
            WHERE sweep_id = ?
        """
        params: list[Any] = [sweep_id]
        if config is not None:
            query += " AND config_json = ?"
            params.append(_config_json(config))
        if rep is not None:
            query += " AND rep = ?"
            params.append(rep)
        if name is not None:
            query += " AND name = ?"
            params.append(name)
        query += " ORDER BY rep, attempt, name, path"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            IndexedArtifact(
                sweep_id=str(row[0]),
                case_key=str(row[1]),
                rep=int(row[2]),
                attempt=int(row[3]),
                name=str(row[4]),
                path=str(row[5]),
                kind=str(row[6]),
                size_bytes=int(row[7]),
                config=json.loads(row[8]),
                created_at=str(row[9]),
            )
            for row in rows
        ]

    def clear_artifacts(self, sweep_id: str) -> None:
        """Delete all indexed artifacts for one sweep id."""
        with self.connect() as conn:
            conn.execute("DELETE FROM artifacts WHERE sweep_id = ?", (sweep_id,))

    def sync_artifacts_from_log(self, *, sweep_id: str, log_path: str) -> None:
        """Rebuild indexed artifacts for one sweep from the canonical JSONL log."""
        self.clear_artifacts(sweep_id)
        path = Path(log_path)
        if not path.exists():
            return
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            row = json.loads(raw_line)
            if row.get("sweep_id") != sweep_id:
                continue
            config = row.get("config", {})
            artifacts = row.get("artifacts", [])
            if not isinstance(config, dict) or not isinstance(artifacts, list) or not artifacts:
                continue
            entry_case_key = row.get("case_key")
            if not isinstance(entry_case_key, str) or not entry_case_key:
                continue
            self.record_artifacts(
                sweep_id=sweep_id,
                case_key=entry_case_key,
                rep=int(row.get("rep", 0)),
                attempt=int(row.get("attempt", 1)),
                config=config,
                artifacts=[artifact for artifact in artifacts if isinstance(artifact, dict)],
            )

    def clear_resume_cases(self, *, benchmark_name: str, log_path: str) -> None:
        """Remove cached resume state for one benchmark/log pair."""
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM resume_cases WHERE benchmark_name = ? AND log_path = ?",
                (benchmark_name, log_path),
            )

    def sync_resume_cases_from_log(self, *, benchmark_name: str, log_path: str) -> None:
        """Rebuild cached case state from the canonical JSONL log."""
        self.clear_resume_cases(benchmark_name=benchmark_name, log_path=log_path)
        path = Path(log_path)
        if not path.exists():
            return

        rows: list[tuple[str, str, int, str, str, str, str]] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            row = json.loads(raw_line)
            row_benchmark = row.get("storage_id", row.get("benchmark"))
            if row_benchmark != benchmark_name:
                continue
            config = row.get("config", {})
            if not isinstance(config, dict):
                continue
            rep = int(row.get("rep", 0))
            logged_case_key = row.get("case_key")
            resolved_case_key = logged_case_key if isinstance(logged_case_key, str) and logged_case_key else ""
            if not resolved_case_key:
                continue
            rows.append(
                (
                    resolved_case_key,
                    benchmark_name,
                    rep,
                    str(row.get("status", "ok")),
                    _config_json(config),
                    log_path,
                    str(row.get("timestamp", "")),
                ),
            )

        if not rows:
            return

        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO resume_cases (
                    case_key,
                    benchmark_name,
                    rep,
                    status,
                    config_json,
                    log_path,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_key) DO UPDATE SET
                    status = excluded.status,
                    config_json = excluded.config_json,
                    log_path = excluded.log_path,
                    updated_at = excluded.updated_at
                """,
                rows,
            )

    def completed_resume_keys(self, *, benchmark_name: str, log_path: str) -> set[str]:
        """Return previously successful resume keys for one benchmark/log pair."""
        self.sync_resume_cases_from_log(benchmark_name=benchmark_name, log_path=log_path)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT case_key
                FROM resume_cases
                WHERE benchmark_name = ?
                  AND log_path = ?
                  AND status = 'ok'
                """,
                (benchmark_name, log_path),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def record_resume_case(
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
        """Insert or update one cached resume-case row."""
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO resume_cases (
                    case_key,
                    benchmark_name,
                    rep,
                    status,
                    config_json,
                    log_path,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_key) DO UPDATE SET
                    status = excluded.status,
                    config_json = excluded.config_json,
                    log_path = excluded.log_path,
                    updated_at = excluded.updated_at
                """,
                (
                    case_key,
                    benchmark_name,
                    rep,
                    status,
                    _config_json(config),
                    log_path,
                    updated_at,
                ),
            )


def log_execution_event(
    *,
    event: str,
    benchmark_id: str,
    sweep_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append one execution event to the global project log."""
    row = {
        "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event,
        "benchmark_id": benchmark_id,
        "sweep_id": sweep_id,
        "payload": payload or {},
    }
    with execution_log_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str, sort_keys=True) + "\n")
