"""Shared reader for the analysis-ready format -- the module analysis code should
import. Works uniformly across whatever data source wrote a given run (see
pywerfl/sources/ and pywerfl.write_data): tables are discovered from whatever
*.parquet files exist in a run's folder, not hardcoded to any one source's sensor
set, and run IDs are treated as opaque strings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class Run:
    run_id: str
    metadata: dict
    tables: dict[str, pd.DataFrame] = field(repr=False)

    def __getattr__(self, name: str) -> pd.DataFrame:
        # Only called when normal attribute lookup fails, so this doesn't shadow
        # run_id/metadata/tables themselves. Lets e.g. run.cp work for any table a
        # source happens to provide, without hardcoding sensor names here.
        try:
            return self.tables[name]
        except KeyError:
            raise AttributeError(
                f"Run {self.run_id!r} has no table {name!r}; available: {sorted(self.tables)}"
            ) from None


def list_runs(analysis_ready_dir: Path) -> list[str]:
    """Run IDs available under analysis_ready_dir, exactly as written (no reformatting),
    sorted as plain strings. Sources with numeric IDs are responsible for their own
    zero-padding if they want string-sort order to match numeric order."""
    return sorted(
        p.name.removeprefix("run_")
        for p in Path(analysis_ready_dir).iterdir()
        if p.is_dir() and p.name.startswith("run_")
    )


def load_run(analysis_ready_dir: Path, run_id: str) -> Run:
    run_dir = Path(analysis_ready_dir) / f"run_{run_id}"
    metadata = json.loads((run_dir / "metadata.json").read_text())
    tables = {p.stem: pd.read_parquet(p) for p in sorted(run_dir.glob("*.parquet"))}
    return Run(run_id=run_id, metadata=metadata, tables=tables)
