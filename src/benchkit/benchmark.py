"""Benchmark decorator."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

from benchkit.result_storage import ResultStorage

from .serialize import Serializer, serialize

logger = logging.getLogger(__name__)


F = TypeVar("F", bound=Callable[..., Any])


def save_benchmark(
    _func: F | None = None,
    *,
    bench_name: str | None = None,
    serializers: dict[type, Serializer] | None = None,
    storage: ResultStorage | None = None,
    repeat: int = 1,
    num_retries: int = 0,
) -> Callable[[F], F]:
    """Decorator to benchmark a function with specified serializers and save results.

    Args:
        _func (F | None): The function to be decorated. If None, returns a decorator.
        bench_name (str | None): Optional name for the benchmark. If None, uses the function name.
        serializers (dict[type, Serializer] | None): Mapping from types to serialization functions.
        storage (Storage | None): Storage backend to save benchmark results. Defaults to ParquetStorage.
        repeat (int): Number of times to repeat the benchmark. Defaults to 1.
        num_retries (int): Number of retries for the benchmark. Defaults to 0.

    Returns:
        A decorator for benchmarking.
    """
    serializers = serializers or {}

    if storage is None:
        storage = ResultStorage(Path("bench_results"))

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: list[Any], **kwargs: dict[str, Any]) -> dict[str, Any]:
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            # Serialize inputs for logging
            inputs = serialize(bound.arguments, serializers)

            last_output = {}

            for i in range(repeat):
                success = False
                raw_output = None

                for attempt in range(num_retries + 1):
                    try:
                        raw_output = func(*args, **kwargs)
                        success = True
                        break
                    except Exception as e:
                        msg = (
                            f"Error in benchmark '{bench_name or func.__name__}' "
                            f"(attempt {attempt + 1}/{num_retries + 1}): {e}"
                        )
                        logger.exception(msg)

                if not success:
                    msg = f"All {num_retries + 1} attempts failed for benchmark '{bench_name or func.__name__}'"
                    logger.error(msg)
                    continue  # Skip storing this failed result

                if not isinstance(raw_output, dict):
                    raw_output = {"result": raw_output}

                outputs = serialize(raw_output, serializers)

                storage.save_benchmark(
                    bench_name=bench_name or func.__name__,
                    inputs=inputs,
                    outputs=outputs,
                    metadata={"m_iter": int(i + 1)},
                )

                last_output = outputs

            return last_output

        return wrapper  # type: ignore[return-value]

    if _func is not None:
        return decorator(_func)

    return decorator
