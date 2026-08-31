"""Static, facility-level reference data bundled with the package."""

from __future__ import annotations

from importlib import resources

import pandas as pd


def load_tap_locations() -> pd.DataFrame:
    path = resources.files(__package__) / "tap_locations.csv"
    with resources.as_file(path) as p:
        return pd.read_csv(p, dtype={"tap_id": str})
