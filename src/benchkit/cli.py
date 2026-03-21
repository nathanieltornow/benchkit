"""Operational CLI for BenchKit inspection and setup."""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from .store import default_store

console = Console()
app = typer.Typer(help="Inspect BenchKit sweeps and runs.")


def _skill_content() -> str:
    """Return the full text of the bundled skill file.

    Returns:
        str: The skill file content.
    """
    path = Path(str(importlib.resources.files("benchkit") / "skill.md"))
    return path.read_text(encoding="utf-8")


def _format_config(config: dict[str, Any], max_len: int = 48) -> str:
    text = ", ".join(f"{key}={value}" for key, value in config.items())
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


def _format_metrics(metrics: Any, max_len: int = 56) -> str:  # noqa: ANN401
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
    """Set up BenchKit in a project directory.

    Appends the full benchkit skill to AGENTS.md so that AI agents
    automatically know how to use benchkit in this project.

    Raises:
        Exit: If the target directory does not exist.
    """
    target_dir = Path(target).resolve() if target else Path.cwd()
    if not target_dir.is_dir():
        console.print(f"[red]Directory {target_dir} does not exist.[/red]")
        raise typer.Exit(1)

    agents_md = target_dir / "AGENTS.md"
    skill = _skill_content()
    marker = "# BenchKit -- Agentic Experiment Skill"

    if agents_md.exists():
        existing = agents_md.read_text(encoding="utf-8")
        if marker in existing:
            console.print("[dim]AGENTS.md already contains the benchkit skill, skipping.[/dim]")
            return
        agents_md.write_text(existing.rstrip() + "\n\n" + skill, encoding="utf-8")
        console.print(f"[green]Appended benchkit skill to {agents_md}[/green]")
    else:
        agents_md.write_text(skill, encoding="utf-8")
        console.print(f"[green]Created {agents_md} with benchkit skill[/green]")


@app.command("install-skill")  # type: ignore[misc]
def install_skill() -> None:
    """Install the BenchKit skill globally for Claude Code.

    Inlines the full benchkit skill into ~/.claude/CLAUDE.md so that
    the agent knows how to use benchkit in every conversation.
    """
    skill = _skill_content()
    marker = "# BenchKit -- Agentic Experiment Skill"

    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True, exist_ok=True)

    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
        if marker in existing:
            console.print("[dim]~/.claude/CLAUDE.md already contains the benchkit skill. Skipping.[/dim]")
            return
        claude_md.write_text(existing.rstrip() + "\n\n" + skill, encoding="utf-8")
        console.print(f"[green]Appended benchkit skill to {claude_md}[/green]")
    else:
        claude_md.write_text(skill, encoding="utf-8")
        console.print(f"[green]Created {claude_md} with benchkit skill[/green]")


def main() -> None:
    """Run the BenchKit CLI."""
    app()


if __name__ == "__main__":
    main()
