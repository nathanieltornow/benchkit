"""Utilities for applying plot defaults."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import matplotlib.pyplot as plt

from .config import PRESETS, base_rc_params, latex_rc_params

if TYPE_CHECKING:
    from collections.abc import Iterator


@contextmanager
def pplot(
    *,
    preset: str | None = None,
    latex: bool = False,
    custom_rc: dict[str, Any] | None = None,
) -> Iterator[None]:
    """Apply BenchKit plot defaults within a context block.

    Args:
        preset: Named figure size preset (e.g. ``"double-column"``, ``"single-column"``).
            See ``benchkit.plot.config.PRESETS`` for available options.
        latex: Enable LaTeX text rendering for publication-quality math labels.
        custom_rc: Optional matplotlib rc overrides applied last.

    Yields:
        None: Context with matplotlib rc params applied.

    Raises:
        ValueError: If the preset name is not recognized.
    """
    rc_params = base_rc_params()
    if latex:
        rc_params.update(latex_rc_params())
    if preset is not None:
        if preset not in PRESETS:
            msg = f"Unknown preset {preset!r}. Available: {', '.join(sorted(PRESETS))}."
            raise ValueError(msg)
        rc_params["figure.figsize"] = PRESETS[preset]
    rc_params.update(custom_rc or {})
    with plt.rc_context(rc=rc_params):
        yield
