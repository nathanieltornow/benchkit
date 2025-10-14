"""Decorator for logging function calls and results to a JSONL file."""

from __future__ import annotations

import datetime as dt
import functools
import inspect
import json
import platform
import uuid
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

import git
import pandas as pd
import rich

from benchkit.config import data_path

if TYPE_CHECKING:
    from collections.abc import Callable

P = ParamSpec("P")
R = TypeVar("R")


def log(log_name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to log function calls and their results.

    Args:
        log_name (str): Name of the log file (without extension).

    Returns:
        Callable[[Callable[P, R]], Callable[P, R]]: The decorated function.
    """
    init_time = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_dir = data_path / "logs"
    log_file = f"{log_name}.jsonl"

    if _is_dirty():
        warnings.warn(
            "You are logging with uncommitted changes. Please make sure to commit your changes for reproducibility.",
            RuntimeWarning,
            stacklevel=2,
        )

    log_path = log_dir / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    rich.print(f"[bold green]Logging to[/bold green] [cyan]{log_path.resolve()}[/cyan]")

    def deco(fn: Callable[P, R]) -> Callable[P, R]:
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            config = dict(bound.arguments)
            # remove self/cls if it's a method/classmethod
            config.pop("self", None)
            config.pop("cls", None)

            result: R = fn(*args, **kwargs)

            entry: dict[str, Any] = {
                "config": config,
                "result": result,
                "id": str(uuid.uuid4())[:8],
                "log_name": log_name,
                "func_name": fn.__name__,
                "init_time": init_time,
                "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "host": platform.node(),
                "git_commit": _get_git_commit(),
            }

            with Path(log_path).open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

            return result

        return wrapper

    return deco


def load(log_name: str) -> pd.DataFrame:
    """Load log entries from a log file.

    Args:
        log_name (str): Name of the log.

    Returns:
        pd.DataFrame: DataFrame containing the log entries.

    Raises:
        FileNotFoundError: If the log file does not exist.
    """
    log_file = f"{log_name}.jsonl"
    log_path = data_path / "logs" / log_file

    if not log_path.exists():
        msg = f"Log file {log_path} does not exist."
        raise FileNotFoundError(msg)

    return pd.json_normalize(pd.read_json(log_path, lines=True).to_dict(orient="records"))


def _get_git_commit() -> str:
    try:
        repo = git.Repo(search_parent_directories=True)
        return str(repo.head.object.hexsha[:7])
    except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
        return "unknown"


def _is_dirty() -> bool:
    try:
        repo = git.Repo(search_parent_directories=True)
        return bool(repo.is_dirty())
    except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
        return True
