"""Benchkit library."""

from __future__ import annotations

from .benchmark import save_benchmark
from .result_storage import ResultStorage

__all__ = ["ResultStorage", "save_benchmark"]
