"""Filesystem-based artifact helpers."""

from __future__ import annotations

import json
import pickle  # noqa: S403
import shutil
import subprocess
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import benchkit_home, ensure_dir
from .store import BenchkitStore


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


def artifact_dir_for(
    *,
    run_id: str | None = None,
    benchmark_id: str | None = None,
    sweep: str | None = None,
    sweep_id: str | None = None,
    case_key: str | None = None,
    rep: int | None = None,
) -> Path:
    """Return the canonical artifact directory for one run.

    Legacy sweep-style arguments are still accepted as a fallback.
    """
    if run_id is not None:
        if benchmark_id is not None and sweep is not None:
            return BenchkitStore().run_dir(
                benchmark_id=benchmark_id,
                sweep_id=sweep,
                run_id=run_id,
            )
        return ensure_dir("artifacts", run_id)
    assert sweep_id is not None
    assert case_key is not None
    assert rep is not None
    return ensure_dir("artifacts", sweep_id, case_key, f"rep-{rep}")


def artifact_index_path() -> Path:
    """Return the central SQLite path used for artifact indexing."""
    root = benchkit_home()
    root.mkdir(parents=True, exist_ok=True)
    return root / "benchmarks.sqlite"


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


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Structured result for one artifact-captured command execution."""

    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    stdout_path: Path
    stderr_path: Path
    metadata_path: Path


@dataclass(slots=True)
class ArtifactIndex:
    """SQLite-backed artifact index."""

    path: Path = field(default_factory=artifact_index_path)

    def __post_init__(self) -> None:
        """Ensure the central store schema exists."""
        BenchkitStore(self.path)

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
        BenchkitStore(self.path).record_artifacts(
            sweep_id=sweep_id,
            case_key=case_key,
            rep=rep,
            attempt=attempt,
            config=config,
            artifacts=artifacts,
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
        rows = BenchkitStore(self.path).list_artifacts(
            sweep_id,
            config=config,
            rep=rep,
            name=name,
        )
        return [
            ArtifactRecord(
                sweep_id=row.sweep_id,
                case_key=row.case_key,
                rep=row.rep,
                attempt=row.attempt,
                name=row.name,
                path=row.path,
                kind=row.kind,
                size_bytes=row.size_bytes,
                config=row.config,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def sync_from_log(self, *, sweep_id: str, log_path: str) -> None:
        """Rebuild indexed artifacts for one sweep from the JSONL log."""
        BenchkitStore(self.path).sync_artifacts_from_log(sweep_id=sweep_id, log_path=log_path)

    def clear_sweep(self, sweep_id: str) -> None:
        """Delete all indexed artifacts for one sweep id."""
        BenchkitStore(self.path).clear_artifacts(sweep_id)


@dataclass(slots=True)
class RunContext:
    """Per-case sweep context for storing artifacts."""

    sweep_id: str
    case_key: str
    rep: int
    benchmark_id: str | None = None
    sweep: str | None = None
    attempt: int | None = None
    benchmark: str | None = None
    system: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    result_row: dict[str, Any] = field(default_factory=dict)
    records: list[dict[str, Any]] = field(default_factory=list)
    run_id: str | None = None

    def __post_init__(self) -> None:
        """Assign a stable opaque run id if needed."""
        if self.run_id is None:
            self.run_id = str(uuid.uuid4())

    @property
    def artifact_dir(self) -> Path:
        """Return the artifact directory for this case."""
        return artifact_dir_for(
            run_id=self.run_id,
            benchmark_id=self.benchmark_id,
            sweep=self.sweep,
        )

    @property
    def metadata_path(self) -> Path:
        """Return the metadata.json location for this run."""
        return self.artifact_dir / "metadata.json"

    @property
    def stdout_path(self) -> Path:
        """Return the stdout capture path for this run."""
        return self.artifact_dir / "stdout.txt"

    @property
    def stderr_path(self) -> Path:
        """Return the stderr capture path for this run."""
        return self.artifact_dir / "stderr.txt"

    @property
    def manifest_path(self) -> Path:
        """Return the artifact manifest path for this run."""
        return self.artifact_dir / "manifest.json"

    @property
    def metrics_path(self) -> Path:
        """Return the canonical metrics file path for this run."""
        return self.artifact_dir / "metrics.json"

    @property
    def results_log_path(self) -> Path:
        """Return the append-only results log path for this run."""
        return self.artifact_dir / "results.jsonl"

    def path_for(self, name: str) -> Path:
        """Return a child path in the artifact directory."""
        path = self.artifact_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def save_bytes(self, name: str, data: bytes) -> str:
        """Store raw bytes and return the artifact path.

        Returns:
            str: Filesystem path of the stored artifact.
        """
        path = self.path_for(name)
        path.write_bytes(data)
        self._record(path, kind="bytes")
        return str(path)

    def save_text(self, name: str, text: str, *, encoding: str = "utf-8") -> str:
        """Store text and return the artifact path.

        Returns:
            str: Filesystem path of the stored artifact.
        """
        path = self.path_for(name)
        path.write_text(text, encoding=encoding)
        self._record(path, kind="text")
        return str(path)

    def save_json(self, name: str, value: Any, *, register: bool = True) -> str:  # noqa: ANN401
        """Store JSON and return the artifact path.

        Returns:
            str: Filesystem path of the stored artifact.
        """
        path = self.path_for(name)
        path.write_text(json.dumps(value, default=str, sort_keys=True, indent=2), encoding="utf-8")
        if register:
            self._record(path, kind="json")
        return str(path)

    def save_pickle(self, name: str, value: Any) -> str:  # noqa: ANN401
        """Store a Python object via pickle and return the artifact path.

        Returns:
            str: Filesystem path of the stored artifact.
        """
        path = self.path_for(name)
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
        target = self.path_for(name or source_path.name)
        shutil.copy2(source_path, target)
        self._record(target, kind="file")
        return str(target)

    def save_file(self, source: str | Path, name: str | None = None) -> str:
        """Copy an existing file into the artifact directory.

        Returns:
            str: Filesystem path of the stored artifact.
        """
        return self.copy_file(source, name=name)

    def save_result(self, value: dict[str, Any]) -> dict[str, Any]:
        """Store the canonical metric row for this run.

        Returns:
            dict[str, Any]: The saved canonical metric row.
        """
        self.result_row = dict(value)
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        self.metrics_path.write_text(
            json.dumps(self.result_row, default=str, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        return dict(self.result_row)

    def append_result(self, value: dict[str, Any]) -> dict[str, Any]:
        """Append one metric sample row for this run.

        Returns:
            dict[str, Any]: The appended sample row.
        """
        row = dict(value)
        self.results_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.results_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, default=str, sort_keys=True) + "\n")
        return row

    def _record(self, path: Path, *, kind: str) -> None:
        record = {
            "name": path.name,
            "path": str(path),
            "kind": kind,
            "size_bytes": path.stat().st_size,
        }
        self.records.append(record)
        self._flush_manifest()

    def _flush_manifest(self) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(self.records, default=str, sort_keys=True, indent=2),
            encoding="utf-8",
        )


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
    """Return the currently active benchmark run context.

    Returns:
        RunContext: The current per-case run context.

    Raises:
        RuntimeError: If no benchmark run is currently active.
    """
    ctx = _CURRENT_CONTEXT.get()
    if ctx is None:
        msg = "No active BenchKit benchmark context. Use benchkit.context() inside a running benchmark function."
        raise RuntimeError(msg)
    return ctx


def run(
    command: str | list[str],
    *,
    name: str | None = None,
    cwd: str | Path | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
    text: bool = True,
) -> CommandResult:
    """Run a command inside the active benchmark case and save outputs as artifacts.

    The command's stdout, stderr, and metadata are written into the active
    artifact directory so later analysis can inspect or derive metrics from the
    raw outputs.

    Returns:
        CommandResult: Captured command outputs and artifact paths.

    Raises:
        subprocess.CalledProcessError: If ``check`` is true and the command fails.
    """
    ctx = context()
    prefix = _command_prefix(ctx, name=name)
    shell = isinstance(command, str)
    completed = subprocess.run(  # noqa: S603
        command,
        check=False,
        capture_output=True,
        cwd=cwd,
        env=env,
        text=text,
        shell=shell,
    )
    stdout = (
        completed.stdout if isinstance(completed.stdout, str) else completed.stdout.decode("utf-8", errors="replace")
    )
    stderr = (
        completed.stderr if isinstance(completed.stderr, str) else completed.stderr.decode("utf-8", errors="replace")
    )

    stdout_path = Path(ctx.save_text(f"{prefix}.stdout.txt", stdout))
    stderr_path = Path(ctx.save_text(f"{prefix}.stderr.txt", stderr))
    command_args = [command] if isinstance(command, str) else [str(part) for part in command]
    metadata = {
        "args": command_args,
        "cwd": str(Path(cwd).resolve()) if cwd is not None else str(Path.cwd()),
        "returncode": completed.returncode,
        "shell": shell,
    }
    metadata_path = Path(ctx.save_json(f"{prefix}.run.json", metadata))

    if check and completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            command,
            output=stdout,
            stderr=stderr,
        )

    return CommandResult(
        args=command_args,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        metadata_path=metadata_path,
    )


def _command_prefix(ctx: RunContext, *, name: str | None) -> str:
    base = name or "command"
    existing = {str(record.get("name")) for record in ctx.records if isinstance(record.get("name"), str)}
    if f"{base}.run.json" not in existing:
        return base
    index = 2
    while f"{base}-{index}.run.json" in existing:
        index += 1
    return f"{base}-{index}"


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
