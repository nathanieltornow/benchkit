"""Benchkit library."""

from __future__ import annotations

from ._version import version as __version__
from ._version import version_tuple as version_info
from .benchmark import save_benchmark
from .plot import pplot
from .storage import ResultStorage, get_storage, load, load_results, save, set_storage

__all__ = [
    "ResultStorage",
    "__version__",
    "get_storage",
    "load",
    "load_results",
    "pplot",
    "save",
    "save_benchmark",
    "set_storage",
    "version_info",
]
