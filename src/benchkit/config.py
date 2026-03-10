"""Shared filesystem configuration for BenchKit."""

from __future__ import annotations

import os
from pathlib import Path


def benchkit_home() -> Path:
    """Return the root directory used for BenchKit outputs."""
    root = os.environ.get("BENCHKIT_HOME")
    return Path(root).expanduser() if root else Path("~/.benchkit").expanduser()


def ensure_dir(*parts: str) -> Path:
    """Create and return a directory below the BenchKit root.

    Returns:
        Path: The created directory.
    """
    path = benchkit_home().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_output_path(path: str | Path, *default_parts: str) -> Path:
    """Resolve a user path or fall back to a default BenchKit location.

    Returns:
        Path: The resolved output path.
    """
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if candidate.parent != Path():
        return candidate
    return benchkit_home().joinpath(*default_parts, candidate.name)
