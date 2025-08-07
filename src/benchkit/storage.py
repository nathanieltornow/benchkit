"""Storage backends for benchmark results."""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import git
import pandas as pd

logger = logging.getLogger("benchkit")


class ResultStorage:
    """Storage backend using Parquet files."""

    def __init__(self, db_path: str | Path = "benchmarks") -> None:
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
        return [d.name for d in self._db_path.iterdir() if d.is_dir()]

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
        self.optimize(bench_name)
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

    def save(
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
save = storage_registry.save
