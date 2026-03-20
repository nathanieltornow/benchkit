"""Benchkit library."""

from __future__ import annotations

from ._version import version as __version__
from ._version import version_tuple as version_info
from .analysis import Analysis, open_analysis
from .artifacts import (
    ArtifactRecord,
    CommandResult,
    RunContext,
    clear_sweep_artifacts,
    context,
    get_artifact,
    list_artifacts,
    load_artifact,
    load_pickle,
    run,
)
from .benchmark import BenchFunction, func, grid
from .logging import Run, iter_runs, join_logs, load_log, load_runs
from .plot import pplot, save_figure

__all__ = [
    "Analysis",
    "ArtifactRecord",
    "BenchFunction",
    "CommandResult",
    "Run",
    "RunContext",
    "__version__",
    "clear_sweep_artifacts",
    "context",
    "func",
    "get_artifact",
    "grid",
    "iter_runs",
    "join_logs",
    "list_artifacts",
    "load_artifact",
    "load_log",
    "load_pickle",
    "load_runs",
    "open_analysis",
    "pplot",
    "run",
    "save_figure",
    "version_info",
]
