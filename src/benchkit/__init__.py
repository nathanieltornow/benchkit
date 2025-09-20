"""Benchkit library."""

from __future__ import annotations

from ._version import version as __version__
from ._version import version_tuple as version_info
from .benchmark import store
from .loops import foreach
from .plot import pplot
from .storage import ResultStorage, dump, get_storage, load, load_results, set_storage

__all__ = [
    "ResultStorage",
    "__version__",
    "dump",
    "foreach",
    "get_storage",
    "load",
    "load_results",
    "pplot",
    "store",
    "set_storage",
    "version_info",
]
