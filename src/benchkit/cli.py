"""Operational CLI for BenchKit inspection and setup."""

from __future__ import annotations

import importlib.resources
import shutil
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from .store import default_store

console = Console()
app = typer.Typer(help="Inspect BenchKit sweeps and runs.")


def _skill_source() -> Path:
    """Return the path to the bundled SKILL.md shipped with the package.

    Returns:
        Path: The skill file path.
    """
    return Path(str(importlib.resources.files("benchkit") / "skill.md"))


def _format_config(config: dict[str, Any], max_len: int = 48) -> str:
    """Format a compact config preview for tables.

    Returns:
        str: Truncated config string.
    """
    text = ", ".join(f"{key}={value}" for key, value in config.items())
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


def _format_metrics(metrics: Any, max_len: int = 56) -> str:  # noqa: ANN401
    """Format a compact metrics preview for tables.

    Returns:
        str: Truncated metrics string.
    """
    text = ", ".join(f"{key}={value}" for key, value in metrics.items()) if isinstance(metrics, dict) else str(metrics)
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


@app.command("sweeps")  # type: ignore[misc]
def sweeps_list(
    benchmark_id: Annotated[str | None, typer.Argument(help="Optional benchmark id.")] = None,
) -> None:
    """List registered sweeps.

    Raises:
        Exit: If no sweeps are found.
    """
    records = default_store().list_sweeps(benchmark=benchmark_id)
    if not records:
        console.print("[dim]No sweeps found.[/dim]")
        raise typer.Exit

    table = Table(title="sweeps", title_justify="left", box=None, show_edge=False, pad_edge=False, expand=True)
    table.add_column("Benchmark", header_style="dim")
    table.add_column("Sweep", header_style="dim")
    table.add_column("Runs", justify="right", header_style="dim")
    table.add_column("Created", header_style="dim")
    for row in records:
        table.add_row(row["benchmark"], row["sweep"], str(row["count"]), row["created_at"])
    console.print(table)


@app.command("runs")  # type: ignore[misc]
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
        console.print("[dim]No sweeps found.[/dim]")
        raise typer.Exit

    rows = default_store().query_runs(
        benchmark=benchmark_id,
        sweep=resolved_sweep,
        status=status,
    )
    if not rows:
        console.print("[dim]No runs found.[/dim]")
        raise typer.Exit

    table = Table(title="runs", title_justify="left", box=None, show_edge=False, pad_edge=False, expand=True)
    table.add_column("Sweep", header_style="dim")
    table.add_column("Status", header_style="dim")
    table.add_column("Config", header_style="dim")
    table.add_column("Metrics", header_style="dim")
    table.add_column("Created", header_style="dim")
    for row in rows:
        error = row.get("error")
        status_str = row["status"]
        if isinstance(error, dict):
            status_str = f"{status_str} ({error.get('type', '')})"
        table.add_row(
            row["sweep"],
            status_str,
            _format_config(row.get("config", {})),
            _format_metrics(row.get("metrics", {})),
            row.get("created_at", ""),
        )
    console.print(table)


@app.command()  # type: ignore[misc]
def init(
    target: Annotated[str | None, typer.Argument(help="Target project directory.")] = None,
) -> None:
    """Install the BenchKit skill into a project.

    Creates .claude/skills/benchkit/SKILL.md so Claude Code
    auto-discovers the benchkit skill in this project.

    Raises:
        Exit: If the target directory does not exist.
    """
    target_dir = Path(target).resolve() if target else Path.cwd()
    if not target_dir.is_dir():
        console.print(f"[red]Directory {target_dir} does not exist.[/red]")
        raise typer.Exit(1)

    _install_skill_to(target_dir / ".claude" / "skills" / "benchkit")


@app.command("install-skill")  # type: ignore[misc]
def install_skill() -> None:
    """Install the BenchKit skill globally for Claude Code.

    Creates ~/.claude/skills/benchkit/SKILL.md so the skill
    is available in every Claude Code conversation.
    """
    _install_skill_to(Path.home() / ".claude" / "skills" / "benchkit")


def _install_skill_to(skill_dir: Path) -> None:
    """Copy the bundled SKILL.md into a target skill directory.

    Raises:
        Exit: If the bundled skill file is missing.
    """
    source = _skill_source()
    if not source.exists():
        console.print("[red]Could not find bundled skill file.[/red]")
        raise typer.Exit(1)

    skill_dir.mkdir(parents=True, exist_ok=True)
    dest = skill_dir / "SKILL.md"

    if dest.exists():
        existing = dest.read_text(encoding="utf-8")
        new = source.read_text(encoding="utf-8")
        if existing == new:
            console.print(f"[dim]{dest} is already up to date.[/dim]")
            return

    shutil.copy2(source, dest)
    console.print(f"[green]Installed skill to {dest}[/green]")


def main() -> None:
    """Run the BenchKit CLI."""
    app()


if __name__ == "__main__":
    main()
