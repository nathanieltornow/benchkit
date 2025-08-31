"""Decorator for iterating over a list of values for a specific parameter."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


P = ParamSpec("P")
R = TypeVar("R")


def foreach(**iters: Iterable[Any]) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator for iterating over a list of values for specific parameters.

    Args:
        **iters (Iterable[Any]): Keyword arguments where the key is the parameter
            name and the value is an iterable of values.

    Returns:
        Callable[[Callable[P, R]], Callable[P, R]]: The decorated function.
    """
    names = tuple(iters.keys())
    cols = tuple(iters.values())

    def deco(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # If caller fixed all names, just call once
            if all(n in kwargs for n in names):
                return fn(*args, **kwargs)

            for row in zip(*cols, strict=True):  # strict zip -> lengths must match
                call_kwargs = dict(kwargs)
                for n, v in zip(names, row):
                    # allow partial fixing: if user set n, keep it; else use v
                    call_kwargs.setdefault(n, v)
                last = fn(*args, **call_kwargs)  # type: ignore[arg-type]
            return last

        return wrapper

    return deco
