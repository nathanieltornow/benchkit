"""Benchmark decorator."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from functools import wraps
from itertools import chain
from pathlib import Path
from typing import Any, TypeAlias, TypeVar

from benchkit.result_storage import ResultStorage, Scalar

Serializer: TypeAlias = Callable[[Any], dict[str, Scalar] | Scalar]


logger = logging.getLogger(__name__)


F = TypeVar("F", bound=Callable[..., Any])


def save_benchmark(
    _func: F | None = None,
    *,
    serializers: dict[type, Serializer] | None = None,
    storage: ResultStorage | None = None,
    repeat: int = 1,
) -> Callable[[F], F]:
    """Decorator to benchmark a function with specified serializers and save results.

    Args:
        _func (F | None): The function to be decorated. If None, returns a decorator.
        serializers (dict[type, Serializer] | None): Mapping from types to serialization functions.
        storage (Storage | None): Storage backend to save benchmark results. Defaults to ParquetStorage.
        repeat (int): Number of times to repeat the benchmark. Defaults to 1.

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
            inputs = dict(
                chain.from_iterable(
                    _safe_serialize(name, val, serializers).items() for name, val in bound.arguments.items()
                )
            )

            last_output = {}

            for i in range(repeat):
                raw_output = func(*args, **kwargs)

                if not isinstance(raw_output, dict):
                    raw_output = {"result": raw_output}

                outputs = dict(
                    chain.from_iterable(
                        _safe_serialize(name, val, serializers).items() for name, val in raw_output.items()
                    )
                )

                storage.save_benchmark(
                    func_name=func.__name__,
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


def _safe_serialize(arg_name: str, val: object, serializers: dict[type, Serializer]) -> dict[str, Scalar]:
    """Safely serialize a value using the provided serializers.

    Args:
        arg_name (str): Name of the argument being serialized.
        val (object): Value to serialize.
        serializers (dict[type, Serializer]): Mapping from types to serialization functions.

    Returns:
        dict[str, Scalar]: Serialized value as a dictionary.

    Raises:
        TypeError: If the value cannot be serialized.
    """
    if isinstance(val, Scalar):
        return {arg_name: val}

    for type_, serializer in serializers.items():
        if isinstance(val, type_):
            val = serializer(val)

    if isinstance(val, dict):
        flat_dict = _flatten_dict(val, prefix=arg_name + "_")
        if any(not isinstance(v, Scalar) for v in flat_dict.values()):
            msg = f"Cannot serialize nested type for argument '{arg_name}'."
            raise TypeError(msg)
        return flat_dict

    msg = f"Unsupported type for argument '{arg_name}': {type(val)}"
    raise TypeError(msg)


def _flatten_dict(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a nested dictionary with prefixed keys.

    Args:
        d (dict[str, Any]): Dictionary to flatten.
        prefix (str): Prefix for the keys.

    Returns:
        dict[str, Any]: Flattened dictionary with prefixed keys.
    """
    flattened = {}
    for key, value in d.items():
        new_key = f"{prefix}{key}"
        if isinstance(value, dict):
            flattened.update(_flatten_dict(value, f"{new_key}_"))
        else:
            flattened[new_key] = value
    return flattened
