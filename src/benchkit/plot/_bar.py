from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from .config import default_error_kw, get_style

if TYPE_CHECKING:
    import pandas as pd
    from matplotlib.axes import Axes


def bar_comparison(
    ax: Axes,
    results: pd.DataFrame,
    keys: list[str],
    group_key: str,
    *,
    error: Literal["std", "sem", "ci95"] | None = "ci95",
) -> None:
    """Plot a bar comparison on the given Axes.

    Args:
        ax (Axes): Matplotlib Axes to plot on.
        results (pd.DataFrame): DataFrame containing the results data.
        keys (list[str]): List of column names for the bars.
        group_key (str): Column name for grouping the bars.
        error (Literal["std", "sem", "ci95"] | None, optional): Type of error bars to display.
            "std" for standard deviation, "sem" for standard error of the mean,
            "ci95" for 95% confidence interval. If None, no error bars are shown. Defaults to "ci95".
    """
    groups = sorted(results[group_key].dropna().unique(), key=lambda g: get_style(str(g)).sort_order)
    x = range(len(keys))
    total_width = 0.8
    num_groups = len(groups)
    bar_width = total_width / num_groups
    offsets = [(i - num_groups / 2) * bar_width + bar_width / 2 for i in range(num_groups)]

    for offset, group in zip(offsets, groups, strict=True):
        group_data = results[results[group_key] == group]
        means = [group_data[key].mean() for key in keys]

        errors = None
        match error:
            case "std":
                errors = [group_data[key].std() for key in keys]
            case "sem":
                errors = [group_data[key].sem() for key in keys]
            case "ci95":
                errors = [1.96 * group_data[key].sem() if len(group_data[key]) > 1 else 0 for key in keys]

        config = get_style(str(group))

        ax.bar(
            [xi + offset for xi in x],
            means,
            width=bar_width,
            label=group,
            yerr=errors,
            hatch=config.hatch,
            facecolor=config.color,
            error_kw=default_error_kw() if errors is not None else None,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(keys)
