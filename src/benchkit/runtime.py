"""Active benchmark runtime context and command execution helpers."""

from __future__ import annotations

import json
import pickle  # noqa: S403
import shutil
import subprocess
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import RunStatus, capture_env
from .store import BenchkitStore


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
class RunContext:
    """Per-case benchmark runtime context for storing artifacts and results."""

    sweep_id: str
    case_key: str
    benchmark_id: str
    artifact_dir_path: Path
    db_path: str
    config: dict[str, Any] = field(default_factory=dict)
    records: list[dict[str, Any]] = field(default_factory=list)
    _rep: int = 0
    _has_result: bool = False

    @property
    def artifact_dir(self) -> Path:
        """Return the artifact directory, creating it if needed."""
        self.artifact_dir_path.mkdir(parents=True, exist_ok=True)
        return self.artifact_dir_path

    def path_for(self, name: str) -> Path:
        """Return a path for a named artifact."""
        path = self.artifact_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def save_bytes(self, name: str, data: bytes) -> str:
        """Save binary data as a named artifact.

        Returns:
            str: The path to the saved file.
        """
        path = self.path_for(name)
        path.write_bytes(data)
        self._record(path, kind="bytes")
        return str(path)

    def save_text(self, name: str, text: str, *, encoding: str = "utf-8") -> str:
        """Save text data as a named artifact.

        Returns:
            str: The path to the saved file.
        """
        path = self.path_for(name)
        path.write_text(text, encoding=encoding)
        self._record(path, kind="text")
        return str(path)

    def save_json(self, name: str, value: Any, *, register: bool = True) -> str:  # noqa: ANN401
        """Save a JSON artifact.

        Returns:
            str: The path to the saved file.
        """
        path = self.path_for(name)
        path.write_text(json.dumps(value, default=str, sort_keys=True, indent=2), encoding="utf-8")
        if register:
            self._record(path, kind="json")
        return str(path)

    def save_pickle(self, name: str, value: Any) -> str:  # noqa: ANN401
        """Save a pickle artifact.

        Returns:
            str: The path to the saved file.
        """
        path = self.path_for(name)
        with path.open("wb") as handle:
            pickle.dump(value, handle)
        self._record(path, kind="pickle")
        return str(path)

    def copy_file(self, source: str | Path, name: str | None = None) -> str:
        """Copy a file into the artifact directory.

        Returns:
            str: The path to the copied file.
        """
        source_path = Path(source)
        target = self.path_for(name or source_path.name)
        shutil.copy2(source_path, target)
        self._record(target, kind="file")
        return str(target)

    def save_file(self, source: str | Path, name: str | None = None) -> str:
        """Save a file as an artifact (alias for copy_file).

        Returns:
            str: The path to the saved file.
        """
        return self.copy_file(source, name=name)

    def save_result(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """Save one result row to the database.

        Each call writes a separate row with an incrementing repetition counter.
        Call this once per repetition inside the benchmark function.

        Returns:
            dict[str, Any]: A copy of the saved metrics.
        """
        store = BenchkitStore(path=Path(self.db_path))
        store.insert_run(
            benchmark=self.benchmark_id,
            sweep=self.sweep_id,
            case_key=self.case_key,
            rep=self._rep,
            status=RunStatus.OK.value,
            config=self.config,
            metrics=metrics,
            artifact_dir=str(self.artifact_dir_path),
            env=capture_env(),
        )
        self._rep += 1
        self._has_result = True
        return dict(metrics)

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
    """Temporarily install a benchmark run context.

    Yields:
        RunContext: The activated context.
    """
    token = _CURRENT_CONTEXT.set(ctx)
    try:
        yield ctx
    finally:
        _CURRENT_CONTEXT.reset(token)


def context() -> RunContext:
    """Return the currently active benchmark run context.

    Returns:
        RunContext: The active context.

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
    timeout: float | None = None,
) -> CommandResult:
    """Run a command inside the active benchmark case and save outputs as artifacts.

    Returns:
        CommandResult: Structured result with stdout, stderr, and artifact paths.

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
        timeout=timeout,
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
