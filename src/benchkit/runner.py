"""Runner function for executing benchmarks in batch mode."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .benchmark import save_benchmark
from .result_storage import ResultStorage
from .serialize import Serializer, serialize

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

logger = logging.getLogger(__name__)


def run_benchmark_batch(
    func: Callable[[Any], Any],
    inputs: Iterable[dict[str, Any]],
    *,
    bench_name: str | None = None,
    serializers: dict[type, Serializer] | None = None,
    storage: ResultStorage | None = None,
    repeats: int = 1,
    num_retries: int = 0,
) -> None:
    """Run a batch of benchmarks on the provided function with given inputs.

    Args:
        func (Callable): The function to benchmark.
        inputs (Iterable[dict[str, Any]]): A collection of input dictionaries to benchmark.
        bench_name (str | None): Optional name for the benchmark. If None, uses the function name.
        serializers (dict[type, Serializer] | None): Optional serializers for custom types.
        storage (ResultStorage | None): Optional storage backend to save results.
        repeats (int): Number of times to repeat each benchmark. Defaults to 1.
        num_retries (int): Number of retries for each benchmark. Defaults to 0.
    """
    storage = storage or ResultStorage(Path("bench_results"))
    bench_name = bench_name or func.__name__
    serializers = serializers or {}
    safe_func = save_benchmark(
        func,
        bench_name=bench_name,
        serializers=serializers,
        storage=storage,
        repeat=repeats,
        num_retries=num_retries,
    )

    for input_data in inputs:
        existing_results = storage.num_results_with_inputs(
            bench_name=bench_name, inputs=serialize(input_data, serializers)
        )
        if existing_results >= repeats:
            msg = f"Skipping benchmark for {bench_name} with inputs {input_data} as it already has enough results."
            logger.info(msg)
            continue

        safe_func(**input_data)  # type: ignore [call-arg]
        msg = f"Benchmark {bench_name} completed for inputs {input_data}."
        logger.info(msg)
