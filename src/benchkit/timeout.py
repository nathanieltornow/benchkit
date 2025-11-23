"""Production-safe process-based timeout decorator for Benchkit."""

from __future__ import annotations

import functools
import multiprocessing as mp
from typing import TYPE_CHECKING, ParamSpec, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable

P = ParamSpec("P")
R = TypeVar("R")


def _run_and_capture(
    fn: Callable[P, R],
    args: tuple,
    kwargs: dict,
    q: mp.Queue,
) -> None:
    """Worker execution inside separate process.

    Args:
        fn: Function to execute.
        args: Positional arguments for `fn`.
        kwargs: Keyword arguments for `fn`.
        q: Queue to store result or exception.
    """
    try:
        res = fn(*args, **kwargs)
        q.put((True, res))
    except BaseException as e:  # noqa: BLE001
        q.put((False, e))


def timeout(
    seconds: float,
    default: R,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to timeout a function after `seconds` seconds.

    Args:
        seconds: Number of seconds to wait before timing out.
        default: Value to return if timeout occurs.

    Returns:
        Decorated function that returns `default` on timeout.

    Raises:
        ValueError: If `seconds` is not greater than 0.
    """
    if seconds <= 0:
        msg = "seconds must be > 0"
        raise ValueError(msg)

    def deco(fn: Callable[P, R]) -> Callable[P, R]:

        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            q: mp.Queue = mp.Queue(maxsize=1)
            p = mp.Process(target=_run_and_capture, args=(fn, args, kwargs, q))
            p.start()
            p.join(seconds)

            if p.is_alive():
                # timeout: kill worker
                p.terminate()
                p.join()
                return default

            # worker finished: load result
            try:
                success, payload = q.get_nowait()
            except Exception:  # noqa: BLE001
                # abnormal case: nothing in queue
                return default

            if success:
                return cast("R", payload)
            # worker threw an exception → rethrow it here
            raise payload

        return wrapper

    return deco
