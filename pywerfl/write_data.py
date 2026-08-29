"""Shared writer for the analysis-ready format, used by source-ingestion scripts
(see pywerfl/sources/). Analysis code should not need this module -- read data back
with pywerfl.loader instead.

Defines the one place the on-disk shape of the analysis-ready format lives, so every
data source writes it the same way:

    <analysis_ready_dir>/run_<run_id>/<table_name>.parquet   (one or more tables)
    <analysis_ready_dir>/run_<run_id>/metadata.json
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def write_run(analysis_ready_dir: Path, run_id: str, tables: dict[str, pd.DataFrame], metadata: dict) -> None:
    """Write one run's labeled tables and metadata into analysis_ready_dir/run_<run_id>/.

    tables: {table_name: DataFrame} -- any names, any count; each is written as
        <table_name>.parquet. Different sources can provide entirely different
        table sets (e.g. different sensors) without any change here.
    metadata: an arbitrary JSON-serializable dict, written as metadata.json.
        "run_id" and "source" are conventional but not enforced -- nothing here
        assumes a fixed schema, since different sources will have different fields.
    run_id becomes the literal run_<run_id> folder-name suffix. Formatting choices
    (e.g. zero-padding so folders sort correctly as plain strings) are entirely up
    to the calling source module.
    """
    run_dir = Path(analysis_ready_dir) / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    for table_name, df in tables.items():
        df.to_parquet(run_dir / f"{table_name}.parquet")

    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, default=str))
