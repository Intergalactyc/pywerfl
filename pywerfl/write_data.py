"""
Shared writer for the analysis-ready format, used by source-ingestion scripts.

Analysis code should not need this module - use pywerfl.loader instead.

Defines the one place the on-disk shape of the analysis-ready format lives, so every
data source writes it the same way:

    <analysis_ready_dir>/run_<run_id>/<table_name>.parquet   (one or more tables)
    <analysis_ready_dir>/run_<run_id>/metadata.json
    <analysis_ready_dir>/run_<run_id>/derived.json           (optional)
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def write_run(
    analysis_ready_dir: Path,
    run_id: str,
    tables: dict[str, pd.DataFrame],
    metadata: dict,
    derived: dict | None = None,
) -> None:
    """
    Write one run's labeled tables and metadata into analysis_ready_dir/run_<run_id>/.

    tables: {table_name: DataFrame} - any names, any count; each is written as
        <table_name>.parquet. Different sources can provide entirely different
        table sets (e.g. different sensors) without any change here.
    metadata: dict matching pywerfl.schema.METADATA_FIELDS exactly, written as metadata.json.
    derived: optional extra, source-specific fields not part of the metadata contract,
        written as derived.json if given.

    run_id becomes the literal run_<run_id> folder-name suffix.
    Formatting choices (e.g. zero-padding) are up to the calling source module.
    """
    run_dir = Path(analysis_ready_dir) / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    for table_name, df in tables.items():
        df.to_parquet(run_dir / f"{table_name}.parquet")

    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, default=str))
    if derived is not None:
        (run_dir / "derived.json").write_text(json.dumps(derived, indent=2, default=str))
