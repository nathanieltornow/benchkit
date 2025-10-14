"""Configuration for BenchKit."""

from __future__ import annotations

import os
from pathlib import Path


class _Config:
    def __init__(self) -> None:
        """Initialize the configuration."""
        self._path: Path | None = None

    @property
    def path(self) -> Path:
        if self._path is not None:
            return self._path
        env = os.environ.get("BENCHKIT_PATH")
        if env:
            return Path(env).expanduser()

        self._path = Path.cwd() / ".benchkit"
        self._path.mkdir(parents=True, exist_ok=True)
        data_path = self._path / "data"
        data_path.mkdir(parents=True, exist_ok=True)
        plot_path = self._path / "plots"
        plot_path.mkdir(parents=True, exist_ok=True)
        return self._path

    @path.setter
    def path(self, path: str | Path) -> None:
        """Set the folder for storing benchmark data.

        Args:
            path (str | Path): The path to the folder.
        """
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)

    @property
    def data_path(self) -> Path:
        """Get the path to the data folder.

        Returns:
            Path: The path to the data folder.
        """
        return self.path / "data"

    @property
    def plot_path(self) -> Path:
        """Get the path to the plot folder.

        Returns:
            Path: The path to the plot folder.
        """
        return self.path / "plots"


# Singleton instance
config = _Config()
path = config.path
data_path = config.data_path
plot_path = config.plot_path
