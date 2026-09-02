"""
Cp tap data-quality tools: a manual exclusion list (applied at load time, not ingestion) plus
helpers for finding and inspecting suspicious taps (e.g. a stuck or glitching pressure sensor).

Exclusion list: a tap_exclusions.json file in the workspace root (sibling to analysis_ready/ and
clean/ - NOT inside either, since it's hand-curated and not regenerable from the raw source).
Picked up automatically by pywerfl.loader.load_run().

Format: {"<run_id>": ["<tap_id>", ...]}
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from pywerfl import overrides

EXCLUSIONS_FILENAME = "tap_exclusions.json"


def load_exclusions(workspace_dir: Path) -> dict[str, list[str]]:
    """{run_id: [tap_id, ...]} from <workspace_dir>/tap_exclusions.json, or {} if absent."""
    path = Path(workspace_dir) / EXCLUSIONS_FILENAME
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def excluded_taps(workspace_dir: Path, run_id: str) -> list[str]:
    """Excluded tap IDs for run_id, matching the run ID numerically (padded or not)."""
    return overrides.for_run(load_exclusions(workspace_dir), run_id) or []


def tap_diagnostics(series: pd.Series) -> dict:
    """mean/std/min/max/median/mad/n_unique/unique_frac for one tap's raw time series."""
    valid = series.dropna()
    n = len(valid)
    median = valid.median() if n else np.nan
    return {
        "mean": valid.mean() if n else np.nan,
        "std": valid.std() if n else np.nan,
        "min": valid.min() if n else np.nan,
        "max": valid.max() if n else np.nan,
        "median": median,
        "mad": (valid - median).abs().median() if n else np.nan,
        "n_unique": valid.nunique(),
        "unique_frac": valid.nunique() / n if n else np.nan,
    }


def find_suspicious_taps(run, magnitude_threshold: float = 2.0, unique_frac_threshold: float = 0.01) -> pd.DataFrame:
    """
    Cp taps flagged for implausible magnitude (|mean| > magnitude_threshold)
    or suspiciously little variation (unique_frac < unique_frac_threshold).

    For auditing something already on the exclusion list, run this on a Run loaded with exclude_taps=False,
    so already-excluded taps (which load as all NaN and can't trigger either check) don't hide anything.
    """
    rows = {}
    for tap_id in run.cp.columns:
        d = tap_diagnostics(run.cp[tap_id])
        flags = []
        if abs(d["mean"]) > magnitude_threshold:
            flags.append("high_magnitude")
        if d["unique_frac"] < unique_frac_threshold:
            flags.append("low_variation")
        if flags:
            rows[tap_id] = {**d, "flags": ", ".join(flags)}
    result = pd.DataFrame.from_dict(rows, orient="index")
    return result.sort_values("mean", key=lambda s: s.abs(), ascending=False) if len(result) else result
