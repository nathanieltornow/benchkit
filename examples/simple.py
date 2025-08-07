"""Simple benchmark example using BenchKit."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

from benchkit import load_results, pplot, save_benchmark

if TYPE_CHECKING:
    import pandas as pd


@save_benchmark(repeat=3)
def my_benchmark_function(x: int, y: int) -> dict[str, int]:
    """A simple benchmark function that adds two numbers."""  # noqa: DOC201
    return {"result": x + y, "multiply": x * y}


@load_results("archive/my_benchmark_function/2025-08-07-16-11")
@pplot
def plot_my_benchmark(df: pd.DataFrame) -> plt.Figure:
    """Plot the results of the benchmark."""  # noqa: DOC201
    fig, ax = plt.subplots()
    df.plot(x="m_iter", y="result", kind="line", ax=ax, marker="o")
    ax.set_title("Benchmark Results")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Result")
    return fig
