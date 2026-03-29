"""Benchkit library."""

from __future__ import annotations

from ._version import version as __version__
from ._version import version_tuple as version_info
from .analysis import get_run, load_frame, load_runs
from .benchmark import BenchFunction, func, grid
from .models import Run, RunStatus, SweepSummary
from .runtime import CommandResult, RunContext, context, run

__all__ = [
    "BenchFunction",
    "CommandResult",
    "Run",
    "RunContext",
    "RunStatus",
    "SweepSummary",
    "__version__",
    "context",
    "func",
    "get_run",
    "grid",
    "load_frame",
    "load_runs",
    "run",
    "version_info",
]
