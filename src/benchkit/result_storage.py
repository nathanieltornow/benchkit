"""Storage backends for benchmark results."""

from __future__ import annotations

import logging
import platform
import uuid
from datetime import datetime
from pathlib import Path
from typing import TypeAlias

import git
import pandas as pd

Scalar: TypeAlias = str | int | float | bool | None


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
        func_name: str,
        inputs: dict[str, Scalar],
        outputs: dict[str, Scalar],
        metadata: dict[str, Scalar] | None = None,
    ) -> None:
        """Save benchmark results to a Parquet file.

        Args:
            func_name (str): Name of the function being benchmarked.
            inputs (dict[str, Scalar]): Inputs to the function.
            outputs (dict[str, Scalar]): Outputs from the function.
            metadata (dict[str, Scalar] | None): Additional metadata about the benchmark run.
        """
        # Flatten nested dictionaries for storage
        flattened_data = {}

        # Add inputs with prefix
        for key, value in inputs.items():
            flattened_data[f"i_{key}"] = value

        # Add outputs with prefix
        for key, value in outputs.items():
            flattened_data[f"o_{key}"] = value

        flattened_data.update(self.compute_metadata())
        if metadata:
            flattened_data.update(metadata)

        result_df = pd.DataFrame([flattened_data])
        self._add_parquet_file(func_name, result_df)

    def load_benchmark(self, func_name: str) -> pd.DataFrame:
        """Load benchmark results from Parquet files.

        Args:
            func_name (str): Name of the function whose benchmarks are to be loaded.

        Returns:
            pd.DataFrame: A DataFrame containing the benchmark results.

        Raises:
            FileNotFoundError: If no benchmarks are found for the specified function.
        """
        func_dir = self._db_path / func_name
        if not func_dir.exists():
            msg = f"No benchmarks found for function '{func_name}'."
            raise FileNotFoundError(msg)

        files = self._get_parquet_files(func_name)

        dfs = [pd.read_parquet(file) for file in files]
        return pd.concat(dfs, ignore_index=True)

    def _get_parquet_files(self, func_name: str) -> list[Path]:
        """Get all Parquet files for a specific function.

        Args:
            func_name (str): Name of the function whose Parquet files are to be retrieved.

        Returns:
            list[Path]: List of Parquet file paths for the specified function.
        """
        func_dir = self._db_path / func_name
        if not func_dir.exists():
            return []
        return list(func_dir.glob("*.parquet"))

    def optimize(self, func_name: str) -> None:
        """Optimize the storage by combining Parquet files for a function.

        Args:
            func_name (str): Name of the function whose benchmarks are to be optimized.
        """
        try:
            combined_df = self.load_benchmark(func_name)
        except FileNotFoundError:
            msg = f"No benchmarks found for function '{func_name}'. Optimization skipped."
            logger.warning(msg)
            return

        # delete old files
        for file in self._get_parquet_files(func_name):
            file.unlink()

        self._add_parquet_file(func_name, combined_df)

    def _add_parquet_file(self, func_name: str, df: pd.DataFrame) -> None:
        func_dir = self._db_path / func_name
        func_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        file_path = func_dir / f"{date_str}_{str(uuid.uuid4())[:4]}.parquet"
        df.to_parquet(file_path, index=False)


def _get_git_commit() -> str:
    try:
        repo = git.Repo(search_parent_directories=True)
        return str(repo.head.object.hexsha[:7])
    except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
        logger.warning("Not a git repository or no commit found.")
        return "unknown"
