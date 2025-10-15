"""Simple benchmark example using BenchKit."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt

import benchkit as bk


@bk.foreach(n=[1, 2, 3])
@bk.foreach(lr=[0.01, 0.1])
@bk.catch_failures(default={"acc": 0.0, "loss": float("inf")})
@bk.log("hi.jsonl")
def train_model(n: int, lr: float) -> dict[str, float]:
    """Simulate training a model and return accuracy and loss.

    Args:
        n (int): Number of epochs.
        lr (float): Learning rate.

    Returns:
        dict[str, float]: Dictionary with accuracy and loss.
    """
    # Simulate some training logic
    acc = 0.8 + 0.02 * n - 0.01 * lr
    loss = 0.5 - 0.03 * n + 0.01 * lr
    return {"acc": [acc, 1, 3], "loss": loss}


train_model()
df = bk.load_log("hi.jsonl")

print(df)
