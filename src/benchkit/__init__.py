"""Benchkit library."""

from __future__ import annotations

from ._version import version as __version__
from ._version import version_tuple as version_info
from .benchmark import save_benchmark
from .result_storage import ResultStorage
from .serialize import Serializer, serialize

__all__ = [
    "ResultStorage",
    "Serializer",
    "__version__",
    "save_benchmark",
    "serialize",
    "version_info",
]
