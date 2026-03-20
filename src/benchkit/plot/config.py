"""General plotting configuration."""

from __future__ import annotations

from typing import Any

from cycler import cycler


def colors() -> list[str]:
    """Return the default color cycle."""
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
    """Return the default hatches."""
    return ["//", "\\\\", "---", "oo", "..", "xx", "++"]


def base_rc_params() -> dict[str, Any]:
    """Return matplotlib rc parameters for portable publication-style plots."""
    font_size = 7
    return {
        "axes.prop_cycle": cycler("color", colors()),
        # Portable defaults; callers can opt into LaTeX through custom_rc.
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
        "pdf.fonttype": 42,  # TrueType in PDF (note: ignored by usetex in many cases)
        "ps.fonttype": 42,
        # --- Lines (nicer look for paper figs) ---
        "lines.linewidth": 1.6,
        "lines.markersize": 4.5,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        # --- Axes / grid (helpful for barplots) ---
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.grid.which": "major",
        "grid.alpha": 0.3,
        "grid.linewidth": 0.6,
        # --- Bars/Patches (crisp outlines that print well) ---
        "patch.edgecolor": "black",
        "patch.linewidth": 0.7,
        "patch.antialiased": True,
        # --- Hatching (pattern line thickness & color) ---
        "hatch.linewidth": 0.8,
        "hatch.color": "black",
        # --- Ticks (cleaner) ---
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.size": 3.0,
        "ytick.major.size": 3.0,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        # --- Savefig hygiene ---
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "savefig.dpi": 400,
    }
