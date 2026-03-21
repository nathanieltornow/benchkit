"""Utilities for applying plot defaults."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import matplotlib.pyplot as plt

from .config import base_rc_params

if TYPE_CHECKING:
    from collections.abc import Iterator


@contextmanager
def pplot(*, custom_rc: dict[str, Any] | None = None) -> Iterator[None]:
    """Apply BenchKit plot defaults within a context block.

    Args:
        custom_rc: Optional matplotlib rc overrides.
    """
    rc_params = base_rc_params()
    rc_params.update(custom_rc or {})
    with plt.rc_context(rc=rc_params):
        yield
