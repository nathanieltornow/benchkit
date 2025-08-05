"""Benchmark decorator."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import platform
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, TypeAlias, TypeVar

import git

JSONScalar: TypeAlias = str | int | float | bool | None
JSONSerializable: TypeAlias = JSONScalar | list["JSONSerializable"] | dict[str, "JSONSerializable"]


Serializer: TypeAlias = Callable[[Any], JSONSerializable]


logger = logging.getLogger(__name__)


F = TypeVar("F", bound=Callable[..., Any])


def save_benchmark(
    _func: F | None = None,
    *,
    serializers: dict[type, Serializer] | None = None,
    result_path: Path | str = "results",
    repeat: int = 1,
) -> Callable[[F], F]:
    """Decorator to benchmark a function with specified serializers and save results.

    Args:
        serializers: Mapping from types to functions that convert them to JSON-serializable dicts.
        result_path: Directory where results will be stored.
        repeat: How many times to run and save the benchmark function.

    Returns:
        A decorator for benchmarking.
    """
    serializers = serializers or {}

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: list[Any], **kwargs: dict[str, Any]) -> dict[str, Any]:
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            # Serialize inputs for logging
            inputs = {name: _safe_serialize(val, serializers) for name, val in bound.arguments.items()}

            config_hash = _compute_config_hash(inputs, _get_git_commit())
            Path(result_path).mkdir(parents=True, exist_ok=True)

            last_output = {}

            for i in range(repeat):
                raw_output = func(*args, **kwargs)

                if not isinstance(raw_output, dict):
                    raw_output = {"result": raw_output}

                outputs = {name: _safe_serialize(val, serializers) for name, val in raw_output.items()}

                meta = _collect_metadata()
                meta["config_hash"] = config_hash
                meta["repetition"] = i

                timestamp = current_timestamp()
                filename = f"{timestamp}_{i}_{config_hash}.json"
                filepath = Path(result_path) / filename

                with filepath.open("w") as f:
                    json.dump(
                        {"inputs": inputs, "outputs": outputs, "meta": meta},
                        f,
                        indent=2,
                    )

                last_output = outputs

            return last_output

        return wrapper  # type: ignore[return-value]

    if _func is not None:
        return decorator(_func)

    return decorator


def _collect_metadata() -> dict[str, str | int]:
    return {
        "timestamp": current_timestamp(),
        "system": platform.node(),
        "git_commit": _get_git_commit(),
    }


def current_timestamp() -> str:
    """Get the current timestamp in ISO 8601 format.

    Returns:
        str: Current timestamp formatted as 'YYYY-MM-DDTHH-MM-SS'.
    """
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H-%M-%S")


def _get_git_commit() -> str:
    try:
        repo = git.Repo(search_parent_directories=True)
        return str(repo.head.object.hexsha[:7])
    except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
        logger.warning("Not a git repository or no commit found.")
        return "unknown"


def _compute_config_hash(inputs: dict[str, Any], git_commit: str) -> str:
    hasher = hashlib.sha256()
    hasher.update(json.dumps(inputs, sort_keys=True).encode("utf-8"))
    hasher.update(git_commit.encode("utf-8"))
    return hasher.hexdigest()[:8]


def _safe_serialize(val: object, serializers: dict[type, Serializer]) -> JSONSerializable:
    """Safely serialize a value using provided serializers.

    Args:
        val (object): The value to serialize.
        serializers (dict[type, Serializer]): A dictionary mapping types to serialization functions.

    Returns:
        JSONSerializable: A JSON-serializable representation of the value.

    Raises:
        TypeError: If the value cannot be serialized.
    """
    for typo, fn in serializers.items():
        if isinstance(val, typo):
            return fn(val)
    try:
        json.dumps(val)
    except TypeError:
        msg = f"Cannot serialize value of type {type(val)}: {val}"
        raise TypeError(msg) from None
    return val  # type: ignore[return-value]
