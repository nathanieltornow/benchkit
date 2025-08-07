"""Utility functions for pretty plots."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, overload

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

if TYPE_CHECKING:
    from collections.abc import Callable


R = TypeVar("R")
P = ParamSpec("P")


def _save_figures(
    figs: Figure | Iterable[Figure],
    dir_path: Path | str,
    fname: str,
) -> None:
    """Save figure(s) to PDF in a dated directory structure."""
    date_str = datetime.now().astimezone().strftime("%Y-%m-%d-%H-%M")
    out_dir = Path(dir_path) / date_str / fname
    out_dir.mkdir(parents=True, exist_ok=True)

    def _save_one(fig: object, filename: str) -> None:
        if not isinstance(fig, Figure):
            return
        fig.tight_layout()
        fig.savefig(out_dir / filename, dpi=300, bbox_inches="tight")

    if isinstance(figs, Figure):
        _save_one(figs, f"{fname}.pdf")
    elif isinstance(figs, Iterable):
        for i, maybe_fig in enumerate(figs):
            _save_one(maybe_fig, f"{fname}_{i}.pdf")


@overload
def pplot(
    _fn: Callable[P, R],
) -> Callable[P, R]: ...


@overload
def pplot(
    _fn: None = None,
    *,
    dir_path: Path | str = "plots",
    plot_name: str | None = None,
    custom_rc: dict[str, Any] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def pplot(
    _fn: Callable[P, R] | None = None,
    *,
    dir_path: Path | str = "plots",
    plot_name: str | None = None,
    custom_rc: dict[str, Any] | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to save pretty plots.

    Args:
        dir_path (Path | str): Directory to save plots. Defaults to "plots".
        plot_name (str | None): Name of the plot file. If None, uses the function name.
        custom_rc (dict[str, Any] | None): Custom matplotlib rc parameters.

    Returns:
        Callable: Decorator function that wraps the plotting function.
    """
    custom_rc = custom_rc or {}
    rc_params = latex_rc_params()
    rc_params.update(custom_rc)

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with plt.rc_context(rc=rc_params):
                result = fn(*args, **kwargs)
                _save_figures(result, dir_path=dir_path, fname=plot_name or fn.__name__)
                return result

        return wrapper

    if callable(_fn):
        return decorator(_fn)
    return decorator


def latex_rc_params() -> dict[str, Any]:
    """Return matplotlib rc parameters for LaTeX-style plots."""
    return {
        "text.usetex": True,
        "font.family": "serif",
        "font.serif": ["Computer Modern"],
        "font.size": 10,
        "axes.labelsize": 10,
        "axes.titlesize": 10,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "figure.titlesize": 10,
        "pdf.fonttype": 42,  # Use Type 1 fonts in PDF
        "ps.fonttype": 42,  # Use Type 1 fonts in PostScript
    }


def wide_figsize() -> tuple[float, float]:
    """Returns a wide figure size for 2-column plots.

    Returns:
        tuple[float, float]: A tuple representing the width and height of the figure in inches
    """
    return (12, 2.8)


def column_figsize() -> tuple[float, float]:
    """Returns a column figure size for 1-column plots.

    Returns:
        tuple[float, float]: A tuple representing the width and height of the figure in inches
    """
    return (6, 2.8)
