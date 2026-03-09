"""Minimal filesystem-based artifact store."""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path

from .config import ensure_dir


def artifact(data: bytes, file_ext: str) -> str:
    """Store raw bytes as an artifact and return its filepath.

    Args:
        data (bytes): Bytes to store.
        file_ext (str): File extension.

    Returns:
        str: Path to the saved artifact (relative to ARTIFACT_ROOT).
    """
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    uid = str(uuid.uuid4())[:8]
    suffix = file_ext.removeprefix(".")

    folder = ensure_dir("artifacts", today)

    path = folder / f"{uid}.{suffix}"
    path.write_bytes(data)
    return str(path)


def load_artifact(path: str | Path) -> bytes:
    """Load raw bytes from an artifact filepath.

    Args:
        path (str | Path): Path to the artifact file.

    Returns:
        bytes: The loaded bytes.
    """
    return Path(path).read_bytes()
