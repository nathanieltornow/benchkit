"""Timeout decorator using persistent worker subprocesses."""

from __future__ import annotations

import functools
import multiprocessing as mp
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

import cloudpickle

if TYPE_CHECKING:
    from collections.abc import Callable
    from multiprocessing.connection import Connection

P = ParamSpec("P")
R = TypeVar("R")


def _worker_loop(conn: Connection) -> None:
    """Entry point for persistent worker subprocess.

    Continuously receives `(fn_bytes, args, kwargs)` tuples, executes the
    deserialized function, and sends back `(success, payload)` where:

    - success = True, payload = return value
    - success = False, payload = exception

    Args:
        conn: Connection to the parent process.
    """
    try:
        while True:
            data = conn.recv()  # blocking call
            if data == "STOP":
                return

            fn_bytes, args, kwargs = data
            try:
                fn: Callable[..., Any] = cloudpickle.loads(fn_bytes)
                result = fn(*args, **kwargs)
                conn.send((True, result))
            except BaseException as exc:  # noqa: BLE001
                conn.send((False, exc))
    except EOFError:
        # Parent died or pipe closed
        return


class Worker:
    """Persistent worker subprocess executing a cloudpickled function."""

    def __init__(self, fn_bytes: bytes) -> None:
        """Initialize worker with cloudpickled function.

        Args:
            fn_bytes: Cloudpickled function bytes.
        """
        self.fn_bytes = fn_bytes
        self.conn: Connection
        self.proc: mp.Process
        self._start_worker()

    def _start_worker(self) -> None:
        """Start a new worker subprocess."""
        ctx = mp.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe()
        self.conn = parent_conn
        self.proc = ctx.Process(target=_worker_loop, args=(child_conn,))
        self.proc.start()

    def restart(self) -> None:
        """Restart worker after timeout or crash."""
        self.kill()
        self._start_worker()

    def kill(self) -> None:
        """Terminate worker."""
        try:  # noqa: SIM105
            self.conn.send("STOP")
        except Exception:  # noqa: BLE001, S110
            pass

        self.proc.terminate()
        self.proc.join()

    def call(
        self, args: tuple[Any, ...], kwargs: dict[str, Any], timeout: float
    ) -> tuple[bool, Any]:
        """Execute function in worker with a blocking poll timeout.

        Args:
            args: Positional arguments to pass to function.
            kwargs: Keyword arguments to pass to function.
            timeout: Timeout duration (in seconds).

        Returns:
            Tuple of (success, payload) where:
            - success = True, payload = return value
            - success = False, payload = exception

        Raises:
            TimeoutError: If timeout occurs.
        """
        self.conn.send((self.fn_bytes, args, kwargs))

        # Blocking wait—no active polling required.
        if not self.conn.poll(timeout):
            msg = f"Worker timed out after {timeout} seconds"
            raise TimeoutError(msg)

        return self.conn.recv()


def timeout(seconds: float, default: R) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator adding a kill-safe timeout using a persistent worker subprocess.

    Args:
        seconds: Timeout duration (in seconds).
        default: Value to return on timeout.

    Returns:
        A decorated function whose calls are executed in a persistent
        worker subprocess with timeout enforcement.

    Raises:
        ValueError: If `seconds` is non-positive.
    """
    if seconds <= 0:
        msg = "seconds must be > 0"
        raise ValueError(msg)

    def deco(fn: Callable[P, R]) -> Callable[P, R]:
        fn_bytes = cloudpickle.dumps(fn)
        worker = Worker(fn_bytes)

        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                success, payload = worker.call(args, kwargs, timeout=seconds)

                if success:
                    return payload

                # The worker executed, but function raised an exception
                raise payload  # noqa: TRY301

            except TimeoutError:
                # Timeout → restart worker, return default
                worker.restart()
                return default

            except Exception:
                # Worker crashed → restart worker, raise to caller
                worker.restart()
                raise

        return wrapper

    return deco
