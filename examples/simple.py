"""Simple benchmark example using BenchKit."""

from __future__ import annotations

import matplotlib.pyplot as plt

import benchkit as bk


@bk.func("sort-comparison")
def sort_comparison(algorithm: str, size: int) -> None:
    """Benchmark a sorting algorithm on a random array."""
    result = bk.run(
        [
            "python3",
            "-c",
            (
                "import random, time, json; "
                f"data = [random.random() for _ in range({size})];"
                "t0 = time.perf_counter();"
                "sorted(data);"
                "elapsed = (time.perf_counter() - t0) * 1000;"
                "print(json.dumps({'elapsed_ms': elapsed, 'n_elements': len(data)}))"
            ),
        ],
        name="sort",
    )
    import json

    payload = json.loads(result.stdout)
    bk.context().save_result({
        "elapsed_ms": float(payload["elapsed_ms"]),
        "n_elements": int(payload["n_elements"]),
    })


CASES = bk.grid(algorithm=["timsort", "mergesort"], size=[1000, 10000, 100000])


def main() -> None:
    """Run the example benchmark sweep and plot the results."""
    analysis = sort_comparison.sweep(cases=CASES, show_progress=False)
    df = analysis.load_frame()

    with bk.pplot():
        FIGURE_WIDTH_MM = 180.0
        FIGURE_HEIGHT_MM = 45.0
        fig, ax = plt.subplots(figsize=(FIGURE_WIDTH_MM / 25.4, FIGURE_HEIGHT_MM / 25.4))
        summary_df = df.groupby("config.size", as_index=False)[["result.elapsed_ms"]].mean()
        ax.plot(summary_df["config.size"], summary_df["result.elapsed_ms"], marker="o")
        ax.set_xlabel("Array size")
        ax.set_ylabel("Time (ms)")

    analysis.save_figure(fig, plot_name="sort-comparison")
    analysis.save_dataframe(df, "raw-results", file_format="csv")


if __name__ == "__main__":
    main()
