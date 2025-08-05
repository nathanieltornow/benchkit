"""Functions for exporting benchmark results."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def load_results_to_df(folder: str | Path, *, include_meta: bool = False) -> pd.DataFrame:
    """Load benchmark results from JSON files in a directory into a DataFrame.

    Args:
        folder: Path to the directory containing JSON result files.
        include_meta: Whether to include metadata in the DataFrame.

    Returns:
        A pandas DataFrame containing the benchmark results.
    """
    records = []
    for file in Path(folder).glob("*.json"):
        with Path.open(file) as f:
            data = json.load(f)

        record = {
            **{f"input_{k}": v for k, v in data.get("inputs", {}).items()},
            **{f"output_{k}": v for k, v in data.get("outputs", {}).items()},
        }

        if include_meta:
            record.update({f"meta_{k}": v for k, v in data.get("meta", {}).items()})
            record.update({"filename": file.name})

        records.append(record)

    return pd.DataFrame(records)
