"""Command-line interface for Benchkit."""

from __future__ import annotations

import pandas as pd
import typer
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from typer import Exit, secho

from benchkit import get_storage

from ._version import __version__

app = typer.Typer()
console = Console()


@app.command()  # type: ignore [misc]
def version() -> None:
    """Display version information."""
    typer.echo(f"Benchkit version: {__version__}")


@app.command()  # type: ignore [misc]
def info(bench_name: str) -> None:
    """Display information about a specific benchmark or all benchmarks.

    Args:
        bench_name: Name of the benchmark to display info for.

    Raises:
        Exit: If the specified benchmark does not exist.
    """
    storage = get_storage()

    # Try loading the benchmark
    try:
        res_df = storage.load_benchmark(bench_name)
    except FileNotFoundError as e:
        secho(f"[!] Benchmark '{bench_name}' not found.", fg="red", err=True)
        raise Exit(code=1) from e

    # Gather summary stats
    num_total = len(res_df)
    num_hashes = res_df["m_hash"].nunique() if "m_hash" in res_df.columns else "?"

    if "m_timestamp" in res_df.columns:
        timestamps = pd.to_datetime(res_df["m_timestamp"], errors="coerce")
        ts_min = timestamps.min()
        ts_max = timestamps.max()
    else:
        ts_min = ts_max = "?"  # type: ignore[assignment]

    # Format the summary block
    summary_lines = [
        f"[bold]Benchmark:[/bold] {bench_name}",
        f"[bold]Total Results:[/bold] {num_total}",
        f"[bold]Unique Inputs:[/bold] {num_hashes}",
        f"[bold]Earliest Run:[/bold] {ts_min}",
        f"[bold]Latest Run:[/bold] {ts_max}",
    ]

    summary = "\n".join(summary_lines)
    console.print(Panel(Align.left(summary), expand=False, border_style="cyan"))


@app.command()  # type: ignore [misc]
def archive(bench_name: str) -> None:
    """Archive all benchmarks for a specific function.

    Args:
        bench_name (str): Name of the function whose benchmarks are to be archived.

    Raises:
        Exit: If the benchmark does not exist or if an error occurs during archiving.
    """
    storage = get_storage()
    try:
        storage.archive(bench_name)
        console.print(f"[bold green]Archived benchmarks for '{bench_name}' successfully.[/bold green]")
    except FileNotFoundError as e:
        secho(f"[!] No benchmarks found for '{bench_name}'.", fg="red", err=True)
        raise Exit(code=1) from e
    except Exception as e:
        secho(f"[!] Error archiving benchmarks: {e}", fg="red", err=True)
        raise Exit(code=1) from e


@app.command()  # type: ignore [misc]
def ls(*, archive: bool = False) -> None:
    """List available benchmarks or archived benchmarks.

    Args:
        archive (bool): If True, list archived benchmarks. Defaults to False.
    """
    storage = get_storage()

    benchmarks = storage.available_benchmarks()
    if not benchmarks:
        console.print("[yellow]No benchmarks available.[/yellow]")
        return
    console.print("[bold green]Available benchmarks:[/bold green]")
    for b in benchmarks:
        console.print(f" • [cyan]{b}[/cyan]")

    # print information about archived benchmarks if requested
    if archive:
        archived = storage.get_archived_benchmarks()
        if not archived:
            console.print("[yellow]No archived benchmarks available.[/yellow]")
            return
        console.print("[bold green]Archived benchmarks:[/bold green]")
        for bench, files in archived.items():
            console.print(f" • [cyan]{bench}[/cyan]: {len(files)} files")
            for f in files:
                console.print(f"   - {f}")


def main() -> None:
    """Main entry point for the Benchkit CLI."""
    app()


if __name__ == "__main__":
    main()
