"""Benchmark decorator."""

from __future__ import annotations

import inspect
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec

import rich

from .storage import get_storage

if TYPE_CHECKING:
    from collections.abc import Callable


P = ParamSpec("P")
Record = dict[str, Any]


def store(
    _func: Callable[P, Record] | None = None,
    *,
    name: str | None = None,
    min_records: int = 1,
    verbose: bool = False,
) -> Callable[[Callable[P, Record]], Callable[P, Record]] | Callable[P, Record]:
    """Store a function call.

    Args:
        _func (F | None): The function to be decorated. If None, returns a decorator.
        name (str | None): Optional name for the benchmark. If None, uses the function name.
        min_records (int): If the number of existing results is greater than or equal to this, skip the call.
        verbose (bool): If True, print detailed logs. Defaults to False.

    Returns:
        Callable[[Callable[P, Record]], Callable[P, Record]]: The decorated function.
    """
    storage = get_storage()

    def decorator(func: Callable[P, Record]) -> Callable[P, Record]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Record:
            bench_name_ = name or func.__name__
            bound = inspect.signature(func).bind(*args, **kwargs)
            bound.apply_defaults()
            inputs = dict(bound.arguments)

            # optionally drop 'self' / 'cls' here
            inputs.pop("self", None)
            inputs.pop("cls", None)

            if storage.num_results_with_inputs(bench_name_, inputs) >= min_records:
                if verbose:
                    rich.print(f"Skipping store for {bench_name_} with inputs {inputs}")
                return {}

            if verbose:
                rich.print(f":hourglass_flowing_sand: {inputs}")

            output = func(*args, **kwargs)
            if not isinstance(output, dict):
                msg = f"Unexpected output type for '{bench_name_}': {type(output)}"
                raise TypeError(msg)

            if verbose:
                rich.print(f":floppy_disk: {output}")

            storage.save(bench_name_, inputs, output)
            return output

        return wrapper

    if _func is not None:
        return decorator(_func)
    return decorator
