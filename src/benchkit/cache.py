"""SQLite-based caching decorator."""

from __future__ import annotations

import functools
import hashlib
import pickle  # noqa: S403
import sqlite3
from collections.abc import Callable
from typing import TYPE_CHECKING, ParamSpec, TypeVar, cast

import rich

from benchkit.config import data_path

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

P = ParamSpec("P")
R = TypeVar("R")


def cache(
    name: str, min_hits: int = 1, *, verbose: bool = False
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to cache function results in SQLite after N executions.

    Args:
        name: Cache file name (without extension).
        min_hits: Number of executions required before skipping.
                  E.g. min_hits=3 means the function will run twice,
                  then on the 3rd call it starts skipping.
        verbose: If True, print detailed logs. Defaults to False.

    Returns:
        A decorated function that caches results.
    """
    dbfile: Path = data_path / f"{name}.db"
    conn = sqlite3.connect(dbfile)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS cache (
               key TEXT PRIMARY KEY,
               value BLOB,
               count INTEGER NOT NULL DEFAULT 0
           )"""
    )

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            raw: bytes = pickle.dumps((args, kwargs))
            key: str = hashlib.sha256(raw).hexdigest()

            cur = conn.execute("SELECT value, count FROM cache WHERE key=?", (key,))
            row = cur.fetchone()
            if row is not None:
                value, count = row
                count += 1
                conn.execute("UPDATE cache SET count=? WHERE key=?", (count, key))
                conn.commit()
                if count >= min_hits:
                    if verbose:
                        rich.print(
                            f":fast_forward: Skipping {func.__name__} with args={args}, kwargs={kwargs}"
                        )
                    return cast("R", pickle.loads(value))  # noqa: S301

            if verbose:
                rich.print(
                    f":hourglass_flowing_sand: {func.__name__} with args={args}, kwargs={kwargs}"
                )
            # Compute fresh
            result: R = func(*args, **kwargs)
            if row is None:
                conn.execute(
                    "INSERT INTO cache (key, value, count) VALUES (?, ?, ?)",
                    (key, pickle.dumps(result), 1),
                )
            else:
                conn.execute(
                    "UPDATE cache SET value=?, count=? WHERE key=?",
                    (pickle.dumps(result), count, key),
                )
            conn.commit()
            return result

        return wrapper

    return decorator
