"""Simple benchmark example using BenchKit."""

from __future__ import annotations

import time

import matplotlib.pyplot as plt

import benchkit as bk


def train_model(n: int, lr: float) -> dict[str, float]:
    """Simulate training and return metrics."""
    if n == 3 and lr == 0.1:
        time.sleep(0.02)
    acc = 0.8 + 0.02 * n - 0.01 * lr
    loss = 0.5 - 0.03 * n + 0.01 * lr
    bk.context().save_json("metrics.json", {"n": n, "lr": lr, "acc": acc, "loss": loss})
    bk.context().save_pickle("metrics.pkl", {"acc": acc, "loss": loss})
    return {"acc": acc, "loss": loss}


def main() -> None:
    """Run the example benchmark sweep and plot the results."""
    sweep = bk.Sweep(
        id="simple",
        fn=train_model,
        params={"n": [1, 2, 3], "lr": [0.01, 0.1]},
        repeat=5,
        timeout_seconds=1,
        continue_on_failure=True,
        default_result={"acc": 0.0, "loss": float("inf")},
        max_workers=5,
        resume=False,
    )
    sweep.run()
    df = bk.load_log("simple.jsonl")
    artifact = bk.get_artifact(
        "simple",
        config={"n": 1, "lr": 0.01},
        rep=1,
        name="metrics.pkl",
    )
    print(artifact.path)
    print(bk.load_pickle(artifact))

    with bk.pplot():
        fig, ax = plt.subplots()
        bk.line_comparison(ax, df, keys=["result.acc", "result.loss"], group_key="config.n")
        ax.set_title("Training sweep")
        ax.set_xlabel("Epochs")
        ax.legend()

    bk.save_figure(fig, plot_name="simple-metrics")


if __name__ == "__main__":
    main()
