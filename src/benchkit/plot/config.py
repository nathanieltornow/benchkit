"""General plotting configuration."""

from __future__ import annotations

from typing import Any

from cycler import cycler

# Figure size presets in inches (converted from mm).
# Width x height tuples matching common paper formats.
PRESETS: dict[str, tuple[float, float]] = {
    "double-column": (180.0 / 25.4, 45.0 / 25.4),  # ~7.09 x 1.77 in
    "double-column-tall": (180.0 / 25.4, 70.0 / 25.4),  # ~7.09 x 2.76 in
    "single-column": (85.0 / 25.4, 55.0 / 25.4),  # ~3.35 x 2.17 in
    "single-column-tall": (85.0 / 25.4, 85.0 / 25.4),  # ~3.35 x 3.35 in
    "slide": (254.0 / 25.4, 142.875 / 25.4),  # 16:9 slide, 10 x 5.625 in
}


def colors() -> list[str]:
    """Return the default color cycle (Tol qualitative, colorblind-safe).

    Returns:
        list[str]: Hex color strings.
    """
    return [
        "#4477AA",
        "#EE6677",
        "#228833",
        "#CCBB44",
        "#66CCEE",
        "#AA3377",
        "#BBBBBB",
        "#000000",
    ]


def hatches() -> list[str]:
    """Return the default hatches.

    Returns:
        list[str]: Hatch pattern strings.
    """
    return ["//", "\\\\", "---", "oo", "..", "xx", "++"]


def base_rc_params() -> dict[str, Any]:
    """Return matplotlib rc parameters for portable publication-style plots.

    Returns:
        dict[str, Any]: The rc parameter dictionary.
    """
    font_size = 7
    return {
        "axes.prop_cycle": cycler("color", colors()),
        "text.usetex": False,
        "font.family": "serif",
        "font.serif": ["DejaVu Serif", "Times New Roman", "Times"],
        "font.size": font_size,
        "axes.labelsize": font_size,
        "axes.titlesize": font_size,
        "axes.titleweight": "bold",
        "xtick.labelsize": font_size,
        "ytick.labelsize": font_size,
        "legend.fontsize": font_size,
        "figure.titlesize": font_size + 1,
        # --- Embedding/fonts in vector backends ---
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        # --- Lines ---
        "lines.linewidth": 1.6,
        "lines.markersize": 4.5,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        # --- Axes / grid ---
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.grid.which": "major",
        "grid.alpha": 0.3,
        "grid.linewidth": 0.6,
        # --- Bars/Patches ---
        "patch.edgecolor": "black",
        "patch.linewidth": 0.7,
        "patch.antialiased": True,
        # --- Hatching ---
        "hatch.linewidth": 0.8,
        "hatch.color": "black",
        # --- Ticks ---
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.size": 3.0,
        "ytick.major.size": 3.0,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        # --- Savefig ---
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "savefig.dpi": 400,
    }


def latex_rc_params() -> dict[str, Any]:
    """Return rc overrides for LaTeX text rendering.

    Returns:
        dict[str, Any]: LaTeX-specific rc parameters.
    """
    return {
        "text.usetex": True,
        "font.family": "serif",
        "font.serif": ["Computer Modern Roman"],
        "mathtext.fontset": "cm",
    }
