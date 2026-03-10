"""Utilities for applying plot defaults and saving figures."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import rich
from matplotlib.figure import Figure

from ..config import benchkit_home
from .config import base_rc_params

DEFAULT_PLOT_DIR = benchkit_home() / "plots"
DEFAULT_EXTENSIONS = ["pdf"]


@contextmanager
def pplot(*, custom_rc: dict[str, Any] | None = None) -> Iterator[None]:
    """Apply BenchKit plot defaults within a context block.

    Args:
        custom_rc: Optional matplotlib rc overrides.
    """
    rc_params = base_rc_params()
    rc_params.update(custom_rc or {})
    with plt.rc_context(rc=rc_params):
        yield


def save_figure(
    figs: Figure | Iterable[Figure],
    *,
    plot_name: str,
    dir_path: Path | str = DEFAULT_PLOT_DIR,
    extensions: list[str] | None = None,
) -> list[Path]:
    """Save one or more figures in a timestamped directory structure.

    Args:
        figs: Figure or iterable of figures to save.
        plot_name: Base name for the output directory and files.
        dir_path: Root output directory.
        extensions: File extensions to write. Defaults to PDF only.

    Returns:
        list[Path]: Paths to the saved files.
    """
    if extensions is None:
        extensions = DEFAULT_EXTENSIONS

    date_str = datetime.now().astimezone().strftime("%Y-%m-%d-%H-%M")
    out_dir = Path(dir_path) / plot_name / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []

    def _save_one(fig: object, filename: str) -> None:
        if not isinstance(fig, Figure):
            return
        output_path = out_dir / filename
        fig.tight_layout()
        fig.savefig(output_path, dpi=400, bbox_inches="tight")
        saved_paths.append(output_path)
        rich.print(f":floppy_disk: Saved plot to [bold]{output_path}[/bold]")

    if isinstance(figs, Figure):
        for extension in extensions:
            _save_one(figs, f"{plot_name}.{extension}")
    elif isinstance(figs, Iterable):
        for i, maybe_fig in enumerate(figs):
            for extension in extensions:
                _save_one(maybe_fig, f"{plot_name}_{i}.{extension}")

    return saved_paths
