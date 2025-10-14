"""Benchkit library."""

from __future__ import annotations

from ._version import version as __version__
from ._version import version_tuple as version_info
from .config import path
from .logging import load, log
from .loops import catch_failures, foreach, retry
from .plot import pplot

__all__ = [
    "__version__",
    "catch_failures",
    "foreach",
    "load",
    "log",
    "path",
    "pplot",
    "retry",
    "version_info",
]
