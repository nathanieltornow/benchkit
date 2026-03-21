"""Benchkit library."""

from __future__ import annotations

from ._version import version as __version__
from ._version import version_tuple as version_info
from .analysis import Analysis, open_analysis
from .benchmark import BenchFunction, func, grid
from .logging import Run, RunStatus
from .plot import pplot
from .runtime import CommandResult, RunContext, context, run

__all__ = [
    "Analysis",
    "BenchFunction",
    "CommandResult",
    "Run",
    "RunContext",
    "RunStatus",
    "__version__",
    "context",
    "func",
    "grid",
    "open_analysis",
    "pplot",
    "run",
    "version_info",
]
