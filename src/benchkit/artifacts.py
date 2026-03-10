"""Filesystem-based artifact helpers."""

from __future__ import annotations

import datetime as dt
import json
import pickle  # noqa: S403
import shutil
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import benchkit_home, ensure_dir


def load_artifact(path: str | Path | ArtifactRecord) -> bytes:
    """Load raw bytes from an artifact path or record.

    Args:
        path (str | Path | ArtifactRecord): Artifact path or artifact record.

    Returns:
        bytes: The loaded bytes.
    """
    artifact_path = Path(path.path if isinstance(path, ArtifactRecord) else path)
    return artifact_path.read_bytes()


def load_pickle(path: str | Path | ArtifactRecord) -> Any:  # noqa: ANN401
    """Load a pickled Python object from an artifact path or record.

    Returns:
        Any: The unpickled Python object.
    """
    artifact_path = Path(path.path if isinstance(path, ArtifactRecord) else path)
    with artifact_path.open("rb") as handle:
        return pickle.load(handle)  # noqa: S301


def artifact_dir_for(*, sweep_id: str, case_key: str, rep: int) -> Path:
    """Return the canonical artifact directory for one sweep case."""
    return ensure_dir("artifacts", sweep_id, case_key, f"rep-{rep}")


def artifact_index_path() -> Path:
    """Return the SQLite path used for artifact indexing."""
    return ensure_dir("state") / "artifacts.sqlite"


def _config_json(config: dict[str, Any]) -> str:
    return json.dumps(config, default=str, sort_keys=True)


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """Indexed artifact metadata."""

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


@dataclass(slots=True)
class ArtifactIndex:
    """SQLite-backed artifact index."""

    path: Path = field(default_factory=artifact_index_path)

    def __post_init__(self) -> None:
        """Create the backing artifact index schema if needed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
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
                """
            )

    def record_many(
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
        with sqlite3.connect(self.path) as conn:
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

    def list(
        self,
        sweep_id: str,
        *,
        config: dict[str, Any] | None = None,
        rep: int | None = None,
        name: str | None = None,
    ) -> list[ArtifactRecord]:
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
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            ArtifactRecord(
                sweep_id=row[0],
                case_key=row[1],
                rep=row[2],
                attempt=row[3],
                name=row[4],
                path=row[5],
                kind=row[6],
                size_bytes=row[7],
                config=json.loads(row[8]),
                created_at=row[9],
            )
            for row in rows
        ]

    def clear_sweep(self, sweep_id: str) -> None:
        """Delete all indexed artifacts for one sweep id."""
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM artifacts WHERE sweep_id = ?", (sweep_id,))


@dataclass(slots=True)
class RunContext:
    """Per-case sweep context for storing artifacts."""

    sweep_id: str
    case_key: str
    rep: int
    records: list[dict[str, Any]] = field(default_factory=list)

    @property
    def artifact_dir(self) -> Path:
        """Return the artifact directory for this case."""
        return artifact_dir_for(sweep_id=self.sweep_id, case_key=self.case_key, rep=self.rep)

    def save_bytes(self, name: str, data: bytes) -> str:
        """Store raw bytes and return the artifact path.

        Returns:
            str: Filesystem path of the stored artifact.
        """
        path = self.artifact_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self._record(path, kind="bytes")
        return str(path)

    def save_text(self, name: str, text: str, *, encoding: str = "utf-8") -> str:
        """Store text and return the artifact path.

        Returns:
            str: Filesystem path of the stored artifact.
        """
        path = self.artifact_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
        self._record(path, kind="text")
        return str(path)

    def save_json(self, name: str, value: Any) -> str:  # noqa: ANN401
        """Store JSON and return the artifact path.

        Returns:
            str: Filesystem path of the stored artifact.
        """
        path = self.artifact_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, default=str, sort_keys=True, indent=2), encoding="utf-8")
        self._record(path, kind="json")
        return str(path)

    def save_pickle(self, name: str, value: Any) -> str:  # noqa: ANN401
        """Store a Python object via pickle and return the artifact path.

        Returns:
            str: Filesystem path of the stored artifact.
        """
        path = self.artifact_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(value, handle)
        self._record(path, kind="pickle")
        return str(path)

    def copy_file(self, source: str | Path, name: str | None = None) -> str:
        """Copy an existing file into the case artifact directory.

        Returns:
            str: Filesystem path of the stored artifact.
        """
        source_path = Path(source)
        target = self.artifact_dir / (name or source_path.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        self._record(target, kind="file")
        return str(target)

    def _record(self, path: Path, *, kind: str) -> None:
        self.records.append({
            "name": path.name,
            "path": str(path),
            "kind": kind,
            "size_bytes": path.stat().st_size,
        })


_CURRENT_CONTEXT: ContextVar[RunContext | None] = ContextVar(
    "benchkit_run_context",
    default=None,
)


@contextmanager
def activated_context(ctx: RunContext) -> Any:  # noqa: ANN401
    """Temporarily install a sweep run context.

    Yields:
        RunContext: The active run context for the current case.
    """
    token = _CURRENT_CONTEXT.set(ctx)
    try:
        yield ctx
    finally:
        _CURRENT_CONTEXT.reset(token)


def context() -> RunContext:
    """Return the currently active sweep run context.

    Returns:
        RunContext: The current per-case run context.

    Raises:
        RuntimeError: If no sweep case is currently active.
    """
    ctx = _CURRENT_CONTEXT.get()
    if ctx is None:
        msg = "No active BenchKit sweep context. Use benchkit.context() inside a running Sweep case."
        raise RuntimeError(msg)
    return ctx


def list_artifacts(
    sweep_id: str,
    *,
    config: dict[str, Any] | None = None,
    rep: int | None = None,
    name: str | None = None,
) -> list[ArtifactRecord]:
    """Return artifacts matching the provided sweep context."""
    return ArtifactIndex().list(sweep_id, config=config, rep=rep, name=name)


def get_artifact(
    sweep_id: str,
    *,
    config: dict[str, Any],
    rep: int,
    name: str,
) -> ArtifactRecord:
    """Return one artifact selected by sweep id, config, repetition, and name.

    Raises:
        FileNotFoundError: If no matching artifact exists.
        ValueError: If multiple artifacts match the selector.
    """
    matches = list_artifacts(sweep_id, config=config, rep=rep, name=name)
    if not matches:
        msg = f"No artifact found for sweep_id={sweep_id!r}, config={config!r}, rep={rep}, name={name!r}"
        raise FileNotFoundError(msg)
    if len(matches) > 1:
        msg = f"Multiple artifacts found for sweep_id={sweep_id!r}, config={config!r}, rep={rep}, name={name!r}"
        raise ValueError(msg)
    return matches[0]


def clear_sweep_artifacts(sweep_id: str) -> None:
    """Delete all stored artifacts for one sweep id."""
    ArtifactIndex().clear_sweep(sweep_id)
    root = benchkit_home() / "artifacts" / sweep_id
    if root.exists():
        shutil.rmtree(root)
