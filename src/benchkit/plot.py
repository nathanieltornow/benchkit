"""Utility functions for pretty plots."""

from __future__ import annotations

import inspect
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, Union, overload

import matplotlib.pyplot as plt

from .storage import load

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd

P = ParamSpec("P")
F = TypeVar("F", bound=plt.Figure)
Return = Union[plt.Figure, list[plt.Figure]]


@overload
def plot_results(
    data_source: str, *, out_path: str | Path = "figs"
) -> Callable[[Callable[[pd.DataFrame], Return]], Callable[[], Return]]: ...


@overload
def plot_results(
    *, out_path: str | Path = "figs", **data_sources: str
) -> Callable[[Callable[..., Return]], Callable[[], Return]]: ...


def plot_results(
    data_source: str | None = None,
    *,
    out_path: str | Path = "figs",
    **data_sources: str,
) -> Callable[[Callable[..., Return]], Callable[[], Return]]:
    """Decorator to plot and save benchmark results.

    Usage:
        @plot_results("my_results")
        def single_plot(df):
            return plt.figure()

        @plot_results(train="train_results", test="test_results")
        def comparison_plot(train, test):
            return plt.figure()

    Args:
        data_source: Single result name for functions taking one DataFrame
        out_path: Directory to save the plots. Defaults to "figs".
        **data_sources: Named data sources mapping to function parameters

    Returns:
        A decorator that wraps the function to save its plot output.
    """

    def decorator(fn: Callable[..., Return]) -> Callable[[], Return]:
        # Validate parameters at decoration time
        sig = inspect.signature(fn)

        if data_source is not None:
            # Single data source mode
            if len(sig.parameters) != 1:
                msg = (
                    f"Function '{fn.__name__}' must take exactly one parameter "
                    f"when using single data source, got {len(sig.parameters)}"
                )
                raise TypeError(msg)
        else:
            # Multiple data sources mode - check parameter names match
            expected_params = set(sig.parameters.keys())
            provided_params = set(data_sources.keys())

            if provided_params != expected_params:
                missing = expected_params - provided_params
                extra = provided_params - expected_params
                error_parts = []
                if missing:
                    error_parts.append(f"missing: {', '.join(missing)}")
                if extra:
                    error_parts.append(f"unexpected: {', '.join(extra)}")

                msg = (
                    f"Function '{fn.__name__}' parameters do not match provided data sources: {', '.join(error_parts)}"
                )
                raise TypeError(msg)

        @wraps(fn)
        def wrapper() -> Return:
            def _save_figures(figs: list[plt.Figure] | plt.Figure, subdir: str, fname: str) -> None:
                date_str = datetime.now().astimezone().strftime("%Y-%m-%d-%H-%M")
                out_dir = Path(out_path) / date_str / subdir
                out_dir.mkdir(parents=True, exist_ok=True)

                if isinstance(figs, list):
                    for i, fig in enumerate(figs):
                        fig.tight_layout()
                        fig.savefig(out_dir / f"{fname}_{i}.pdf", dpi=300, bbox_inches="tight")
                else:
                    figs.tight_layout()
                    figs.savefig(out_dir / f"{fname}.pdf", dpi=300, bbox_inches="tight")

            with plt.rc_context(rc=latex_rc_params()):
                if data_source is not None:
                    # Single data source
                    loaded_df = load(data_source)
                    result = fn(loaded_df)
                    subdir = data_source
                else:
                    # Multiple data sources
                    loaded_data = {name: load(source) for name, source in data_sources.items()}
                    result = fn(**loaded_data)
                    subdir = "_".join(data_sources.values())

                _save_figures(result, subdir, fn.__name__)
                return result

        return wrapper

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
