"""Operational CLI for BenchKit inspection and setup."""

from __future__ import annotations

import argparse
import importlib.resources
import shutil
import sys
from pathlib import Path
from typing import Any

from .store import default_store

_SKILLS = ["benchkit", "benchkit-plot"]


def _skills_dir() -> Path:
    """Return the path to the bundled skills directory.

    Returns:
        Path: The skills directory inside the installed package.
    """
    return Path(str(importlib.resources.files("benchkit") / "skills"))


def _format_config(config: dict[str, Any], max_len: int = 48) -> str:
    """Format a compact config preview.

    Returns:
        str: Truncated config string.
    """
    text = ", ".join(f"{key}={value}" for key, value in config.items())
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


def _format_metrics(metrics: Any, max_len: int = 56) -> str:  # noqa: ANN401
    """Format a compact metrics preview.

    Returns:
        str: Truncated metrics string.
    """
    text = ", ".join(f"{key}={value}" for key, value in metrics.items()) if isinstance(metrics, dict) else str(metrics)
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


def _cmd_sweeps(args: argparse.Namespace) -> None:
    records = default_store().list_sweeps(benchmark=args.benchmark)
    if not records:
        print("No sweeps found.")  # noqa: T201
        return
    print(f"{'Benchmark':<24} {'Sweep':<28} {'Runs':>5}  {'Created'}")  # noqa: T201
    for row in records:
        print(f"{row['benchmark']:<24} {row['sweep']:<28} {row['count']:>5}  {row['created_at']}")  # noqa: T201


def _cmd_runs(args: argparse.Namespace) -> None:
    resolved_sweep = args.sweep or default_store().latest_sweep(args.benchmark)
    if resolved_sweep is None:
        print("No sweeps found.")  # noqa: T201
        return
    rows = default_store().query_runs(
        benchmark=args.benchmark,
        sweep=resolved_sweep,
        status=args.status,
    )
    if not rows:
        print("No runs found.")  # noqa: T201
        return
    print(f"{'Status':<12} {'Config':<48} {'Metrics'}")  # noqa: T201
    for row in rows:
        error = row.get("error")
        status_str = row["status"]
        if isinstance(error, dict):
            status_str = f"{status_str}({error.get('type', '')})"
        config = _format_config(row.get("config", {}))
        metrics = _format_metrics(row.get("metrics", {}))
        print(f"{status_str:<12} {config:<48} {metrics}")  # noqa: T201


def _cmd_init(args: argparse.Namespace) -> None:
    target_dir = Path(args.target).resolve() if args.target else Path.cwd()
    if not target_dir.is_dir():
        print(f"Directory {target_dir} does not exist.", file=sys.stderr)  # noqa: T201
        sys.exit(1)
    for skill_name in _SKILLS:
        _install_skill(skill_name, target_dir / ".claude" / "skills" / skill_name)


def _cmd_install_skill(_args: argparse.Namespace) -> None:
    for skill_name in _SKILLS:
        _install_skill(skill_name, Path.home() / ".claude" / "skills" / skill_name)


def _install_skill(skill_name: str, dest_dir: Path) -> None:
    """Copy one bundled skill into a target directory."""
    source = _skills_dir() / skill_name / "SKILL.md"
    if not source.exists():
        print(f"Could not find bundled skill {skill_name!r}.", file=sys.stderr)  # noqa: T201
        sys.exit(1)

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "SKILL.md"

    if dest.exists() and dest.read_text(encoding="utf-8") == source.read_text(encoding="utf-8"):
        print(f"{dest} is already up to date.")  # noqa: T201
        return

    shutil.copy2(source, dest)
    print(f"Installed {skill_name} skill to {dest}")  # noqa: T201


def main() -> None:
    """Run the BenchKit CLI."""
    parser = argparse.ArgumentParser(prog="benchkit", description="Inspect BenchKit sweeps and runs.")
    sub = parser.add_subparsers(dest="command")

    p_sweeps = sub.add_parser("sweeps", help="List registered sweeps.")
    p_sweeps.add_argument("benchmark", nargs="?", default=None, help="Optional benchmark id.")
    p_sweeps.set_defaults(func=_cmd_sweeps)

    p_runs = sub.add_parser("runs", help="List runs for a benchmark.")
    p_runs.add_argument("benchmark", help="Benchmark id.")
    p_runs.add_argument("--sweep", default=None, help="Filter by sweep id.")
    p_runs.add_argument("--status", default=None, help="Filter by run status.")
    p_runs.set_defaults(func=_cmd_runs)

    p_init = sub.add_parser("init", help="Install BenchKit skills into a project.")
    p_init.add_argument("target", nargs="?", default=None, help="Target project directory.")
    p_init.set_defaults(func=_cmd_init)

    p_install = sub.add_parser("install-skill", help="Install BenchKit skills globally.")
    p_install.set_defaults(func=_cmd_install_skill)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
