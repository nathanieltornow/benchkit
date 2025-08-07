"""Benchkit library."""

from __future__ import annotations

from ._version import version as __version__
from ._version import version_tuple as version_info
from .benchmark import save_benchmark
from .serialize import Serializer, serialize
from .storage import ResultStorage, get_storage, load, save, set_storage

__all__ = [
    "ResultStorage",
    "Serializer",
    "__version__",
    "get_storage",
    "load",
    "save",
    "save_benchmark",
    "serialize",
    "set_storage",
    "version_info",
]
