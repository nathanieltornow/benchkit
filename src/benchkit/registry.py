"""Compatibility wrapper for central BenchKit storage."""

from __future__ import annotations

from .store import (
    BenchkitStore,
    IndexedRun,
    SweepRecord,
    execution_log_path,
    log_execution_event,
)
from .store import (
    store_path as registry_path,
)

BenchmarkRegistry = BenchkitStore

__all__ = [
    "BenchmarkRegistry",
    "IndexedRun",
    "SweepRecord",
    "execution_log_path",
    "log_execution_event",
    "registry_path",
]
