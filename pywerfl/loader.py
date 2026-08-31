"""
Shared reader for the analysis-ready format. Import this module in analysis code.
Should be source-naive (loads common format that works for any source).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from pywerfl import workspace


def _resolve_analysis_ready_dir(analysis_ready_dir: Path | None) -> Path:
    if analysis_ready_dir is not None:
        return Path(analysis_ready_dir)
    return workspace.default_workspace() / "analysis_ready"


def _resolve_run_id(run_id: int | str, analysis_ready_dir: Path) -> str:
    """
    Accept an int (or a numeric string, perhaps without zero-padding) by
    matching it against the available runs' numeric values
    """
    run_id_str = str(run_id)
    if (analysis_ready_dir / f"run_{run_id_str}").exists():
        return run_id_str
    if run_id_str.isdigit():
        for candidate in list_runs(analysis_ready_dir):
            if candidate.isdigit() and int(candidate) == int(run_id_str):
                return candidate
    raise FileNotFoundError(f"No run matching {run_id!r} found under {analysis_ready_dir}")


@dataclass
class Run:
    run_id: str
    metadata: dict
    tables: dict[str, pd.DataFrame] = field(repr=False)

    def __getattr__(self, name: str) -> pd.DataFrame:
        try:
            return self.tables[name]
        except KeyError:
            raise AttributeError(
                f"Run {self.run_id!r} has no table {name!r}; available: {sorted(self.tables)}"
            ) from None


def list_runs(analysis_ready_dir: Path | None = None) -> list[str]:
    """
    Run IDs available under analysis_ready_dir (default: the default workspace),
    exactly as written, sorted as plain strings.
    """
    analysis_ready_dir = _resolve_analysis_ready_dir(analysis_ready_dir)
    return sorted(
        p.name.removeprefix("run_")
        for p in analysis_ready_dir.iterdir()
        if p.is_dir() and p.name.startswith("run_")
    )


def load_run(run_id: int | str, analysis_ready_dir: Path | None = None) -> Run:
    analysis_ready_dir = _resolve_analysis_ready_dir(analysis_ready_dir)
    run_id = _resolve_run_id(run_id, analysis_ready_dir)
    run_dir = analysis_ready_dir / f"run_{run_id}"
    metadata = json.loads((run_dir / "metadata.json").read_text())
    tables = {p.stem: pd.read_parquet(p) for p in sorted(run_dir.glob("*.parquet"))}
    return Run(run_id=run_id, metadata=metadata, tables=tables)
