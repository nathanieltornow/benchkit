"""Simple benchmark example using BenchKit."""

from __future__ import annotations

import time

import matplotlib.pyplot as plt

import benchkit as bk


@bk.func("simple")
def simple(n: int, lr: float) -> None:
    """Simulate one benchmark case and write raw outputs into the run folder."""
    if n == 3 and lr == 0.1:
        time.sleep(0.02)
    acc = 0.8 + 0.02 * n - 0.01 * lr
    loss = 0.5 - 0.03 * n + 0.01 * lr
    bk.context().save_json("raw.json", {"n": n, "lr": lr, "acc": acc, "loss": loss})
    bk.context().save_pickle("metrics.pkl", {"acc": acc, "loss": loss})
    bk.context().save_result({"acc": acc, "loss": loss})


BENCH = simple
CASES = bk.grid(n=[1, 2, 3], lr=[0.01, 0.1])


def main() -> None:
    """Run the example benchmark sweep and plot the results."""
    analysis = simple.sweep(
        cases=CASES,
        timeout_seconds=1,
        max_workers=5,
        show_progress=False,
    )
    df = analysis.load_frame()
    run = analysis.get_run(config={"n": 1, "lr": 0.01}, rep=1, status="ok")
    print(run.path("metrics.pkl"))
    print(run.load_pickle("metrics.pkl"))

    with bk.pplot():
        fig, ax = plt.subplots()
        summary_df = df.groupby("config.n", as_index=False)[["result.acc", "result.loss"]].mean()
        ax.plot(summary_df["config.n"], summary_df["result.acc"], marker="o", label="acc")
        ax.plot(summary_df["config.n"], summary_df["result.loss"], marker="s", label="loss")
        ax.set_title("Training sweep")
        ax.set_xlabel("Epochs")
        ax.legend()

    report_dir = analysis.paths.root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "summary.md").write_text(
        "# simple\n\n## Rerun\n\n`uv run python examples/simple.py`\n",
        encoding="utf-8",
    )
    analysis.save_figure(fig, plot_name="simple-metrics")


if __name__ == "__main__":
    main()
