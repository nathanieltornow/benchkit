"""Benchkit library."""

from __future__ import annotations

from ._version import version as __version__
from ._version import version_tuple as version_info
from .benchmark import save
from .plot import pplot
from .storage import ResultStorage, dump, get_storage, load, load_results, set_storage

__all__ = [
    "ResultStorage",
    "__version__",
    "dump",
    "get_storage",
    "load",
    "load_results",
    "pplot",
    "save",
    "set_storage",
    "version_info",
]
