"""Storage backends for benchmark results."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import platform
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, overload

import git
import pandas as pd

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("benchkit")


class ResultStorage:
    """Storage backend using Parquet files."""

    def __init__(self, db_path: str | Path = "bench_results") -> None:
        """Initialize the Parquet storage backend.

        Args:
            db_path (str | Path): Path to the directory where Parquet files will be stored.
        """
        self._db_path = Path(db_path)
        self._db_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_metadata() -> dict[str, str | int]:
        """Collect metadata about the storage backend.

        Returns:
            dict[str, str | int]: Metadata about the storage backend.
        """
        return {
            "m_timestamp": datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S"),
            "m_system": platform.node(),
            "m_git_commit": _get_git_commit(),
        }

    def available_benchmarks(self) -> list[str]:
        """List all available benchmarks in the storage.

        Returns:
            list[str]: List of benchmark names (function names).
        """
        return [d.name for d in self._db_path.iterdir() if d.is_dir() and d.name != "archive"]

    def get_archived_benchmarks(self) -> dict[str, list[str]]:
        """List all archived benchmarks in the storage.

        Returns:
            dict[str, list[str]]: Dictionary mapping benchmark names to lists paths of their names.
        """
        archive_dir = self._db_path / "archive"
        if not archive_dir.exists():
            return {}

        archived_benchmarks = {}
        for bench_dir in archive_dir.iterdir():
            if bench_dir.is_dir():
                archived_benchmarks[bench_dir.name] = [
                    f"archive/{bench_dir.name}/{f.name}" for f in bench_dir.iterdir()
                ]
        return archived_benchmarks

    def save_benchmark(
        self,
        bench_name: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Save benchmark results to a Parquet file.

        Args:
            bench_name (str): Name of the function being benchmarked.
            inputs (dict[str, Any]): Inputs to the function.
            outputs (dict[str, Any]): Outputs from the function.
            metadata (dict[str, Any] | None): Additional metadata about the benchmark run.
        """
        # Flatten nested dictionaries for storage
        flattened_data = {
            **inputs,
            **outputs,
        }

        flattened_data.update(self.compute_metadata())
        if metadata:
            flattened_data.update(metadata)

        flattened_data["m_hash"] = compute_input_hash(inputs)

        result_df = pd.DataFrame([flattened_data])
        self._add_parquet_file(bench_name, result_df)

    def load_benchmark(self, bench_name: str) -> pd.DataFrame:
        """Load benchmark results from Parquet files.

        Args:
            bench_name (str): Name of the function whose benchmarks are to be loaded.

        Returns:
            pd.DataFrame: A DataFrame containing the benchmark results.

        Raises:
            FileNotFoundError: If no benchmarks are found for the specified function.
        """
        func_dir = self._db_path / bench_name
        if not func_dir.exists():
            msg = f"No benchmarks found for function '{bench_name}'."
            raise FileNotFoundError(msg)

        files = self._get_parquet_files(bench_name)
        if not files:
            msg = f"No Parquet files found for function '{bench_name}'."
            raise FileNotFoundError(msg)

        dfs = [pd.read_parquet(file) for file in files]
        return pd.concat(dfs, ignore_index=True)

    def _get_parquet_files(self, bench_name: str) -> list[Path]:
        """Get all Parquet files for a specific function.

        Args:
            bench_name (str): Name of the function whose Parquet files are to be retrieved.

        Returns:
            list[Path]: List of Parquet file paths for the specified function.
        """
        func_dir = self._db_path / bench_name
        if not func_dir.exists():
            return []
        return list(func_dir.glob("*.parquet"))

    def optimize(self, bench_name: str) -> None:
        """Optimize the storage by combining Parquet files for a function.

        Args:
            bench_name (str): Name of the function whose benchmarks are to be optimized.
        """
        try:
            combined_df = self.load_benchmark(bench_name)
        except FileNotFoundError:
            msg = f"No benchmarks found for function '{bench_name}'. Optimization skipped."
            logger.warning(msg)
            return

        # delete old files
        for file in self._get_parquet_files(bench_name):
            file.unlink()

        self._add_parquet_file(bench_name, combined_df)

    def num_results_with_inputs(self, bench_name: str, inputs: dict[str, Any]) -> int:
        """Count the number of results for a specific function with given inputs.

        Args:
            bench_name (str): Name of the function.
            inputs (dict[str, Scalar]): Inputs to match.

        Returns:
            int: Number of results matching the inputs.
        """
        if self.is_empty(bench_name):
            return 0
        bench_df = self.load_benchmark(bench_name)
        input_hash = compute_input_hash(inputs)
        return len(bench_df[bench_df["m_hash"] == input_hash])

    def is_empty(self, bench_name: str) -> bool:
        """Check if there are any benchmarks for a specific function.

        Args:
            bench_name (str): Name of the function.

        Returns:
            bool: True if no benchmarks exist for the function, False otherwise.
        """
        return not self._get_parquet_files(bench_name)

    def archive(self, bench_name: str) -> None:
        """Archive all benchmarks for a specific function.

        Args:
            bench_name (str): Name of the function to archive.
        """
        func_dir = self._db_path / bench_name
        if not func_dir.exists():
            msg = f"No benchmarks found for function '{bench_name}'. Archive skipped."
            logger.warning(msg)
            return

        archive_dir = self._db_path / "archive" / bench_name / datetime.now().astimezone().strftime("%Y-%m-%d-%H-%M")
        archive_dir.mkdir(parents=True, exist_ok=True)

        for file in func_dir.glob("*.parquet"):
            file.rename(archive_dir / file.name)

        msg = f"Archived benchmarks for function '{bench_name}' to {archive_dir}."
        logger.info(msg)

    def _add_parquet_file(self, bench_name: str, df: pd.DataFrame) -> None:
        func_dir = self._db_path / bench_name
        func_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        file_path = func_dir / f"{date_str}_{str(uuid.uuid4())[:4]}.parquet"
        df.to_parquet(file_path, index=False)


def compute_input_hash(inputs: dict[str, Any]) -> str:
    """Compute a hash for the given inputs.

    Args:
        inputs (dict[str, Any]): Inputs to compute the hash for.

    Returns:
        str: A short hash of the inputs.
    """
    raw = json.dumps(inputs, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:8]


def _get_git_commit() -> str:
    try:
        repo = git.Repo(search_parent_directories=True)
        return str(repo.head.object.hexsha[:7])
    except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
        logger.warning("Not a git repository or no commit found.")
        return "unknown"


class _StorageRegistry:
    def __init__(self) -> None:
        """Initialize the storage registry with a default ResultStorage instance."""
        self._storage = ResultStorage()

    def set(self, storage: ResultStorage) -> None:
        """Set the storage backend to use.

        Args:
            storage (ResultStorage): The storage backend to set.
        """
        self._storage = storage

    def get(self) -> ResultStorage:
        """Get the current storage backend.

        Returns:
            ResultStorage: The current storage backend instance.
        """
        return self._storage

    def load(self, name: str) -> pd.DataFrame:
        return self._storage.load_benchmark(name)

    def dump(
        self,
        name: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Save benchmark results to the storage.

        Args:
            name (str): Name of the benchmark.
            inputs (dict[str, Any]): Input parameters for the benchmark.
            outputs (dict[str, Any]): Output results of the benchmark.
            metadata (dict[str, Any] | None): Additional metadata for the benchmark.
        """
        self._storage.save_benchmark(name, inputs, outputs, metadata)


# Instantiate a single registry
storage_registry = _StorageRegistry()

# Shortcuts
set_storage = storage_registry.set
get_storage = storage_registry.get
load = storage_registry.load
dump = storage_registry.dump


P = ParamSpec("P")
R = TypeVar("R")


@overload
def load_results(
    result_name: str,
) -> Callable[[Callable[[pd.DataFrame], R]], Callable[[], R]]: ...


@overload
def load_results(
    **source_map: str,
) -> Callable[[Callable[..., R]], Callable[[], R]]: ...


def load_results(*args: str, **kwargs: str) -> Callable[[Callable[..., R]], Callable[[], R]]:
    """Decorator that injects benchmark results into the wrapped function.

    Usage:
        @load_results("qiskit")  # Injects as first argument
        def plot_qiskit(df): ...

        @load_results(qiskit="qiskit", lumina="lumina")
        def plot_both(qiskit, lumina): ...

    Args:
        *args (str): Positional arguments specifying result names.
        **kwargs (str): Keyword arguments specifying result names.

    Returns:
        Callable[[Callable[..., R]], Callable[[], R]]: A decorator that wraps the function
    """

    def decorator(fn: Callable[..., R]) -> Callable[[], R]:
        sig = inspect.signature(fn)

        if args and kwargs:
            msg = "@load_results: Use either positional or keyword arguments, not both."
            raise TypeError(msg)

        if args:
            if len(args) != 1:
                msg = "@load_results: Only one positional argument allowed."
                raise TypeError(msg)
            param_names = list(sig.parameters.keys())
            if len(param_names) != 1:
                msg = f"Function '{fn.__name__}' must take exactly one argument."
                raise TypeError(msg)
            result_name = args[0]

            @wraps(fn)
            def wrapper() -> R:
                res_df = load(result_name)
                return fn(res_df)

            return wrapper

        if kwargs:
            expected_params = set(sig.parameters.keys())
            provided_params = set(kwargs.keys())

            missing = provided_params - expected_params
            if missing:
                msg = f"Function '{fn.__name__}' is missing parameters: {missing}"
                raise TypeError(msg)

            @wraps(fn)
            def wrapper() -> R:
                dataframes = {name: load(result_name) for name, result_name in kwargs.items()}
                return fn(**dataframes)

            return wrapper

        msg = "@load_results: Must provide at least one result name."
        raise TypeError(msg)

    return decorator
