"""Timeout decorator."""

from __future__ import annotations

import functools
import threading
from typing import TYPE_CHECKING, ParamSpec, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable

P = ParamSpec("P")
R = TypeVar("R")


class _Timeout(threading.Thread):
    """Thread wrapper that captures return value or exception."""

    def __init__(self, fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> None:
        super().__init__(daemon=True)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.result: R | None = None
        self.exc: BaseException | None = None

    def run(self) -> None:
        try:
            self.result = self.fn(*self.args, **self.kwargs)
        except BaseException as e:  # noqa: BLE001
            self.exc = e


def timeout(
    seconds: float,
    default: R,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that limits the execution time of a function.

    If the function does not finish within ``seconds``, return ``default``.

    Args:
        seconds (float): Timeout duration in seconds.
        default (R): Value returned if timeout occurs.

    Returns:
        Callable[[Callable[P, R]], Callable[P, R]]: The decorated function.

    Raises:
        ValueError: If seconds <= 0.
    """
    if seconds <= 0:
        msg = "seconds must be > 0"
        raise ValueError(msg)

    def deco(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            worker = _Timeout(fn, *args, **kwargs)
            worker.start()
            worker.join(timeout=seconds)

            # Timeout → return default
            if worker.is_alive():
                return default

            # If finished but raised → re-raise
            if worker.exc is not None:
                raise worker.exc

            # Must have produced a result
            return cast("R", worker.result)

        return wrapper

    return deco
