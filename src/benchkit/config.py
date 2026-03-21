"""Shared filesystem configuration for BenchKit."""

from __future__ import annotations

import os
from pathlib import Path


def _project_root(start: Path | None = None) -> Path:
    """Return the nearest project-like root from the current working tree.

    Returns:
        Path: The detected project root directory.
    """
    current = (start or Path.cwd()).resolve()
    markers = ("pyproject.toml", ".git", "setup.py")
    for candidate in (current, *current.parents):
        if any((candidate / marker).exists() for marker in markers):
            return candidate
    return current


def benchkit_home() -> Path:
    """Return the root directory used for BenchKit outputs.

    Returns:
        Path: The BenchKit home directory.
    """
    root = os.environ.get("BENCHKIT_HOME")
    return Path(root).expanduser() if root else _project_root() / ".benchkit"


def ensure_dir(*parts: str) -> Path:
    """Create and return a directory below the BenchKit root.

    Returns:
        Path: The created directory.
    """
    path = benchkit_home().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path
