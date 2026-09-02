"""
Manual metadata overrides/additions (for e.g. a missing date_time).
Place a metadata_overrides.json file directly in the raw source directory (the
directory passed to a source's ingestion CLI) - it's picked up automatically on every ingestion.

Format: {"<run_id>": {"<metadata_field>": <value>, ...}, ...}.

Applies to run.metadata (pywerfl.schema.METADATA_FIELDS) - unrecognized field names raise via schema.build_metadata when applied.
"""

from __future__ import annotations

import json
from pathlib import Path

FILENAME = "metadata_overrides.json"


def load(source_dir: Path) -> dict[str, dict]:
    """{run_id: {field: value}} from <source_dir>/metadata_overrides.json, or {} if absent."""
    path = Path(source_dir) / FILENAME
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def for_run(all_overrides: dict[str, dict], run_id: str) -> dict:
    """Overrides for run_id, matching numerically regardless of zero-padding."""
    if run_id in all_overrides:
        return all_overrides[run_id]
    if run_id.isdigit():
        for key, value in all_overrides.items():
            if key.isdigit() and int(key) == int(run_id):
                return value
    return {}
