"""Benchkit library."""

from __future__ import annotations

from ._version import version as __version__
from ._version import version_tuple as version_info
from .analysis import Analysis, load_frame, load_runs, open_analysis
from .benchmark import BenchFunction, func, grid
from .models import Run, RunStatus, SweepSummary
from .runtime import CommandResult, RunContext, context, run

__all__ = [
    "Analysis",
    "BenchFunction",
    "CommandResult",
    "Run",
    "RunContext",
    "RunStatus",
    "SweepSummary",
    "__version__",
    "context",
    "func",
    "grid",
    "load_frame",
    "load_runs",
    "open_analysis",
    "run",
    "version_info",
]
