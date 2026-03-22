"""Operational CLI for BenchKit inspection and setup."""

from __future__ import annotations

import importlib.resources
import shutil
from pathlib import Path
from typing import Annotated, Any

import typer

from .store import default_store

app = typer.Typer(help="Inspect BenchKit sweeps and runs.")

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


@app.command("sweeps")  # type: ignore[misc]  # typer decorator
def sweeps_list(
    benchmark_id: Annotated[str | None, typer.Argument(help="Optional benchmark id.")] = None,
) -> None:
    """List registered sweeps.

    Raises:
        Exit: If no sweeps are found.
    """
    records = default_store().list_sweeps(benchmark=benchmark_id)
    if not records:
        typer.echo("No sweeps found.")
        raise typer.Exit

    typer.echo(f"{'Benchmark':<24} {'Sweep':<28} {'Runs':>5}  {'Created'}")
    for row in records:
        typer.echo(f"{row['benchmark']:<24} {row['sweep']:<28} {row['count']:>5}  {row['created_at']}")


@app.command("runs")  # type: ignore[misc]  # typer decorator
def runs_list(
    benchmark_id: str,
    sweep: Annotated[str | None, typer.Option(help="Filter by sweep id.")] = None,
    status: Annotated[str | None, typer.Option(help="Filter by run status.")] = None,
) -> None:
    """List runs for a benchmark.

    Raises:
        Exit: If no sweeps or runs are found.
    """
    resolved_sweep = sweep or default_store().latest_sweep(benchmark_id)
    if resolved_sweep is None:
        typer.echo("No sweeps found.")
        raise typer.Exit

    rows = default_store().query_runs(
        benchmark=benchmark_id,
        sweep=resolved_sweep,
        status=status,
    )
    if not rows:
        typer.echo("No runs found.")
        raise typer.Exit

    typer.echo(f"{'Status':<12} {'Config':<48} {'Metrics'}")
    for row in rows:
        error = row.get("error")
        status_str = row["status"]
        if isinstance(error, dict):
            status_str = f"{status_str}({error.get('type', '')})"
        typer.echo(
            f"{status_str:<12} {_format_config(row.get('config', {})):<48} {_format_metrics(row.get('metrics', {}))}"
        )


@app.command()  # type: ignore[misc]  # typer decorator
def init(
    target: Annotated[str | None, typer.Argument(help="Target project directory.")] = None,
) -> None:
    """Install all BenchKit skills into a project.

    Creates .claude/skills/benchkit/ and .claude/skills/benchkit-plot/
    so Claude Code auto-discovers both skills in this project.

    Raises:
        Exit: If the target directory does not exist.
    """
    target_dir = Path(target).resolve() if target else Path.cwd()
    if not target_dir.is_dir():
        typer.echo(f"Directory {target_dir} does not exist.")
        raise typer.Exit(1)

    for skill_name in _SKILLS:
        _install_skill(skill_name, target_dir / ".claude" / "skills" / skill_name)


@app.command("install-skill")  # type: ignore[misc]  # typer decorator
def install_skill() -> None:
    """Install all BenchKit skills globally for Claude Code.

    Creates ~/.claude/skills/benchkit/ and ~/.claude/skills/benchkit-plot/
    so both skills are available in every Claude Code conversation.
    """
    for skill_name in _SKILLS:
        _install_skill(skill_name, Path.home() / ".claude" / "skills" / skill_name)


def _install_skill(skill_name: str, dest_dir: Path) -> None:
    """Copy one bundled skill into a target directory.

    Raises:
        Exit: If the bundled skill file is missing.
    """
    source = _skills_dir() / skill_name / "SKILL.md"
    if not source.exists():
        typer.echo(f"Could not find bundled skill {skill_name!r}.")
        raise typer.Exit(1)

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "SKILL.md"

    if dest.exists() and dest.read_text(encoding="utf-8") == source.read_text(encoding="utf-8"):
        typer.echo(f"{dest} is already up to date.")
        return

    shutil.copy2(source, dest)
    typer.echo(f"Installed {skill_name} skill to {dest}")


def main() -> None:
    """Run the BenchKit CLI."""
    app()


if __name__ == "__main__":
    main()
