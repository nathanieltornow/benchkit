"""CLI for inspecting BenchKit sweeps and runs."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from .store import default_store


def _format_config(config: dict[str, Any], max_len: int = 48) -> str:
    text = ", ".join(f"{key}={value}" for key, value in config.items())
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


def _format_metrics(metrics: Any, max_len: int = 56) -> str:  # noqa: ANN401
    text = ", ".join(f"{key}={value}" for key, value in metrics.items()) if isinstance(metrics, dict) else str(metrics)
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


def _cmd_sweeps(args: argparse.Namespace) -> None:
    summaries = default_store().list_sweeps(benchmark=args.benchmark)
    if not summaries:
        print("No sweeps found.")  # noqa: T201
        return
    print(f"{'Benchmark':<24} {'Sweep':<28} {'Runs':>5}  {'Created'}")  # noqa: T201
    for s in summaries:
        print(f"{s.benchmark:<24} {s.sweep:<28} {s.count:>5}  {s.created_at}")  # noqa: T201


def _cmd_runs(args: argparse.Namespace) -> None:
    resolved_sweep = args.sweep or default_store().latest_sweep(args.benchmark)
    if resolved_sweep is None:
        print("No sweeps found.")  # noqa: T201
        return
    records = default_store().query_runs(
        benchmark=args.benchmark,
        sweep=resolved_sweep,
        status=args.status,
    )
    if not records:
        print("No runs found.")  # noqa: T201
        return
    print(f"{'Status':<12} {'Config':<48} {'Metrics'}")  # noqa: T201
    for rec in records:
        status_str = rec.status.value
        if rec.error_type is not None:
            status_str = f"{status_str}({rec.error_type})"
        config = _format_config(rec.config)
        metrics = _format_metrics(rec.metrics)
        print(f"{status_str:<12} {config:<48} {metrics}")  # noqa: T201


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

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
