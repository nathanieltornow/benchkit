"""Operational CLI for BenchKit logs, artifacts, and live watching."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.live import Live
from rich.table import Table

from .artifacts import ArtifactRecord, clear_sweep_artifacts, get_artifact, list_artifacts
from .config import benchkit_home, resolve_output_path
from .logging import load_log

console = Console()
app = typer.Typer(help="Manage BenchKit logs, artifacts, and live watch views.")
artifacts_app = typer.Typer(help="Inspect and manage indexed sweep artifacts.")
app.add_typer(artifacts_app, name="artifacts")


def _parse_config_items(items: list[str] | None) -> dict[str, Any] | None:
    """Parse repeated ``key=value`` CLI items into a config dict.

    Returns:
        dict[str, Any] | None: Parsed config selector or ``None`` when omitted.

    Raises:
        typer.BadParameter: If any item is not formatted as ``key=value``.
    """
    if not items:
        return None

    parsed: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            msg = f"Invalid config selector {item!r}; expected key=value."
            raise typer.BadParameter(msg)
        key, raw_value = item.split("=", 1)
        parsed[key] = _parse_scalar(raw_value)
    return parsed


def _parse_scalar(value: str) -> Any:  # noqa: ANN401
    """Parse one CLI scalar value using JSON when possible.

    Returns:
        Any: Parsed scalar value.
    """
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _resolve_log_target(target: str) -> Path:
    """Resolve a sweep id or explicit path to a JSONL log path.

    Returns:
        Path: Resolved JSONL log path.
    """
    candidate = Path(target)
    if candidate.suffix == ".jsonl" or candidate.is_absolute() or candidate.parent != Path():
        return resolve_output_path(candidate, "logs")
    return resolve_output_path(f"{target}.jsonl", "logs")


def _read_recent_entries(log_path: Path, limit: int) -> list[dict[str, Any]]:
    """Read the last ``limit`` JSONL entries from a log file.

    Returns:
        list[dict[str, Any]]: Parsed recent log rows.
    """
    if not log_path.exists():
        return []
    with log_path.open(encoding="utf-8") as handle:
        lines = handle.readlines()[-limit:]
    entries: list[dict[str, Any]] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        entries.append(json.loads(stripped))
    return entries


def _format_config(config: dict[str, Any], max_len: int = 48) -> str:
    """Format a compact config preview for tables.

    Returns:
        str: Truncated human-readable config string.
    """
    text = ", ".join(f"{key}={value}" for key, value in config.items())
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


def _format_result(result: Any, max_len: int = 56) -> str:  # noqa: ANN401
    """Format a compact result preview for tables.

    Returns:
        str: Truncated human-readable result string.
    """
    text = ", ".join(f"{key}={value}" for key, value in result.items()) if isinstance(result, dict) else str(result)
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


def _logs_table(logs: list[Path]) -> Table:
    """Build a table of known log files.

    Returns:
        Table: Renderable table of discovered logs.
    """
    table = Table(
        title="logs",
        title_justify="left",
        box=None,
        show_edge=False,
        pad_edge=False,
        expand=True,
    )
    table.add_column("Sweep", header_style="dim")
    table.add_column("Path", header_style="dim")
    table.add_column("Rows", justify="right", header_style="dim")
    table.add_column("Updated", header_style="dim")

    for path in logs:
        rows = sum(1 for _ in path.open(encoding="utf-8"))
        updated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))
        table.add_row(path.stem, str(path), str(rows), updated)
    return table


def _artifact_table(records: list[ArtifactRecord]) -> Table:
    """Build a table of artifact index rows.

    Returns:
        Table: Renderable table of artifact records.
    """
    table = Table(
        title="artifacts",
        title_justify="left",
        box=None,
        show_edge=False,
        pad_edge=False,
        expand=True,
    )
    table.add_column("Rep", justify="right", header_style="dim")
    table.add_column("Attempt", justify="right", header_style="dim")
    table.add_column("Name", header_style="dim")
    table.add_column("Kind", header_style="dim")
    table.add_column("Config", header_style="dim")
    table.add_column("Path", header_style="dim")

    for record in records:
        table.add_row(
            str(record.rep),
            str(record.attempt),
            record.name,
            record.kind,
            _format_config(record.config),
            record.path,
        )
    return table


def _summary_panel(log_path: Path) -> Table:
    """Build a compact summary table for one log.

    Returns:
        Table: Renderable summary table.
    """
    log_df = load_log(log_path, normalize=False)
    row_count = len(log_df)
    statuses = log_df["status"].value_counts(dropna=False).to_dict() if "status" in log_df else {}
    config_keys: set[str] = set()
    result_keys: set[str] = set()
    for entry in log_df.to_dict(orient="records"):
        config = entry.get("config")
        result = entry.get("result")
        if isinstance(config, dict):
            config_keys.update(config)
        if isinstance(result, dict):
            result_keys.update(result)

    table = Table(
        title=f"summary {log_path.stem}",
        title_justify="left",
        box=None,
        show_edge=False,
        pad_edge=False,
    )
    table.add_column("Field", header_style="dim")
    table.add_column("Value")
    table.add_row("log", str(log_path))
    table.add_row("rows", str(row_count))
    table.add_row("status", str(statuses or {"ok": row_count}))
    table.add_row("config", ", ".join(sorted(config_keys)) or "-")
    table.add_row("result", ", ".join(sorted(result_keys)) or "-")
    return table


def _watch_render(log_path: Path, limit: int) -> Table:
    """Render the live tail view for one log.

    Returns:
        Table: Renderable watch table.
    """
    rows = _read_recent_entries(log_path, limit)
    table = Table(
        title=f"watch {log_path.stem}  {len(rows)} recent rows  {log_path}",
        title_justify="left",
        box=None,
        show_edge=False,
        pad_edge=False,
        expand=True,
    )
    table.add_column("Time", header_style="dim", no_wrap=True)
    table.add_column("Status", header_style="dim", no_wrap=True)
    table.add_column("Rep", justify="right", header_style="dim", no_wrap=True)
    table.add_column("Config", header_style="dim")
    table.add_column("Result", header_style="dim")

    for row in rows:
        table.add_row(
            str(row.get("timestamp", ""))[-8:],
            str(row.get("status", "ok")),
            str(row.get("rep", "")),
            _format_config(row.get("config", {}) if isinstance(row.get("config"), dict) else {}),
            _format_result(row.get("result")),
        )

    return table


@app.command("logs")  # type: ignore[misc]
def logs_list() -> None:
    """List known BenchKit JSONL logs.

    Raises:
        typer.Exit: If no logs are available.
    """
    log_dir = benchkit_home() / "logs"
    logs = sorted(log_dir.glob("*.jsonl"))
    if not logs:
        console.print("[dim]No BenchKit logs found.[/dim]")
        raise typer.Exit
    console.print(_logs_table(logs))


@app.command()  # type: ignore[misc]
def summary(target: str) -> None:
    """Print a compact summary for one sweep log."""
    log_path = _resolve_log_target(target)
    console.print(_summary_panel(log_path))


@app.command()  # type: ignore[misc]
def watch(
    target: str,
    limit: int = typer.Option(12, min=1, help="Number of recent rows to show."),
    interval: float = typer.Option(0.5, min=0.1, help="Refresh interval in seconds."),
) -> None:
    """Live-tail a running benchmark log."""
    log_path = _resolve_log_target(target)
    with Live(_watch_render(log_path, limit), console=console, refresh_per_second=max(1, int(1 / interval))) as live:
        try:
            while True:
                live.update(_watch_render(log_path, limit))
                time.sleep(interval)
        except KeyboardInterrupt:
            return


@artifacts_app.command("list")  # type: ignore[misc]
def artifacts_list(
    sweep_id: str,
    config: Annotated[
        list[str] | None,
        typer.Option("--config", help="Config selector key=value."),
    ] = None,
    rep: Annotated[int | None, typer.Option(help="Filter by repetition.")] = None,
    name: Annotated[str | None, typer.Option(help="Filter by artifact name.")] = None,
) -> None:
    """List indexed artifacts for a sweep.

    Raises:
        typer.Exit: If no matching artifacts exist.
    """
    records = list_artifacts(
        sweep_id,
        config=_parse_config_items(config),
        rep=rep,
        name=name,
    )
    if not records:
        console.print("[dim]No matching artifacts found.[/dim]")
        raise typer.Exit
    console.print(_artifact_table(records))


@artifacts_app.command("get")  # type: ignore[misc]
def artifacts_get(
    sweep_id: str,
    name: Annotated[str, typer.Option(help="Artifact file name.")],
    rep: Annotated[int, typer.Option(help="Repetition index.")],
    config: Annotated[
        list[str],
        typer.Option("--config", help="Config selector key=value."),
    ],
) -> None:
    """Resolve one indexed artifact path."""
    record = get_artifact(
        sweep_id,
        config=_parse_config_items(config) or {},
        rep=rep,
        name=name,
    )
    console.print(record.path)


@artifacts_app.command("clear")  # type: ignore[misc]
def artifacts_clear(
    sweep_id: str,
    yes: Annotated[
        str | None,
        typer.Option("--yes", flag_value="yes", help="Skip the confirmation prompt."),
    ] = None,
) -> None:
    """Delete stored artifacts for one sweep.

    Raises:
        typer.Exit: If the deletion is not confirmed.
    """
    if yes != "yes" and not typer.confirm(f"Delete all artifacts for sweep {sweep_id!r}?"):
        raise typer.Exit
    clear_sweep_artifacts(sweep_id)
    console.print(f"[green]Cleared artifacts for {sweep_id}[/green]")


def main() -> None:
    """Run the BenchKit CLI."""
    app()


if __name__ == "__main__":
    main()
