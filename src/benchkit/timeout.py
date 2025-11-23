"""Kill-safe timeout that works with decorated functions via cloudpickle."""

from __future__ import annotations

import functools
import multiprocessing as mp
from typing import TYPE_CHECKING, ParamSpec, TypeVar

import cloudpickle  # <— new

if TYPE_CHECKING:
    from collections.abc import Callable

P = ParamSpec("P")
R = TypeVar("R")


def _run_cloudpickled(fn_bytes: bytes, args: tuple, kwargs: dict, q: mp.Queue) -> None:
    """Load callable from bytes and execute in worker."""
    fn: Callable[..., R] = cloudpickle.loads(fn_bytes)
    try:
        q.put((True, fn(*args, **kwargs)))
    except BaseException as e:  # noqa: BLE001
        q.put((False, e))


def timeout(seconds: float) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to timeout a function after N seconds using multiprocessing.

    Args:
        seconds: Number of seconds to wait before timing out.

    Returns:
        Decorated function that raises TimeoutError if it runs too long.

    Raises:
        ValueError: If seconds is not positive.
    """
    if seconds <= 0:
        msg = "seconds must be > 0"
        raise ValueError(msg)

    def deco(fn: Callable[P, R]) -> Callable[P, R]:
        fn_bytes = cloudpickle.dumps(fn)  # serialize *this exact wrapper chain*

        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            q: mp.Queue = mp.Queue(maxsize=1)
            p = mp.Process(target=_run_cloudpickled, args=(fn_bytes, args, kwargs, q))
            p.start()
            p.join(seconds)

            if p.is_alive():
                p.terminate()
                p.join()
                msg = f"Function '{fn.__name__}' timed out after {seconds}s"
                raise TimeoutError(msg)

            success, payload = q.get_nowait()
            if success:
                return payload
            raise payload

        return wrapper

    return deco
