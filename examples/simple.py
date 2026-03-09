"""Simple benchmark example using BenchKit."""

from __future__ import annotations

import matplotlib.pyplot as plt

import benchkit as bk


@bk.foreach(n=[1, 2, 3])
@bk.foreach(lr=[0.01, 0.1])
@bk.catch_failures(default={"acc": 0.0, "loss": float("inf")})
@bk.log("simple.jsonl")
def train_model(n: int, lr: float) -> dict[str, float]:
    """Simulate training and return metrics."""
    acc = 0.8 + 0.02 * n - 0.01 * lr
    loss = 0.5 - 0.03 * n + 0.01 * lr
    return {"acc": acc, "loss": loss}


train_model()
df = bk.load_log("simple.jsonl")

print(df)

fig, ax = plt.subplots()
bk.line_comparison(ax, df, keys=["result.acc", "result.loss"], group_key="config.n")
ax.set_title("Training sweep")
ax.set_xlabel("Epochs")
ax.legend()

bk.pplot(plot_name="simple-metrics")(lambda: fig)()
