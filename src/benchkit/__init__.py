"""Benchkit library."""

from __future__ import annotations

from ._version import version as __version__
from ._version import version_tuple as version_info
from .artifacts import (
    ArtifactRecord,
    RunContext,
    artifact,
    clear_sweep_artifacts,
    context,
    get_artifact,
    list_artifacts,
    load_artifact,
    load_artifacts,
    load_pickle,
)
from .caching import cache
from .logging import join_logs, load_log, log
from .loops import catch_failures, foreach, retry
from .plot import bar_comparison, line_comparison, pplot, save_figure, scatter_comparison
from .sweep import Sweep
from .timeout import timeout

__all__ = [
    "ArtifactRecord",
    "RunContext",
    "Sweep",
    "__version__",
    "artifact",
    "bar_comparison",
    "cache",
    "catch_failures",
    "clear_sweep_artifacts",
    "context",
    "foreach",
    "get_artifact",
    "join_logs",
    "line_comparison",
    "list_artifacts",
    "load_artifact",
    "load_artifacts",
    "load_log",
    "load_pickle",
    "log",
    "pplot",
    "retry",
    "save_figure",
    "scatter_comparison",
    "timeout",
    "version_info",
]
