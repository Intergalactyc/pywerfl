"""Column-naming contract for the analysis-ready format.

Fixed units: wind speeds in m/s, temperatures in K,
pressures in kPa, lengths in m, angles in degrees, relative humidity and
turbulence intensity as a fraction (0-1), Cp and other dimensionless
quantities unitless.

met: temperature, relative_humidity, barometric_pressure
    - measured at 13 ft on the tower
sonic: wind_speed, wind_direction, along_wind, cross_wind, north, west, vertical
    - sonic anemometer above the building (standard 33 ft)
tower: same quantities as sonic, prefixed per height
    - UVW propeller anemometers at each height of the tower
cp: tap-ID-keyed (e.g. "13004"), always dimensionless
    - 60001/60002 are reference taps
"""

from __future__ import annotations

import pandas as pd

from pywerfl import units


def build_table(df: pd.DataFrame, column_spec: dict[str, tuple[str, str, str]]) -> pd.DataFrame:
    """column_spec: {source_column: (canonical_name, source_unit, canonical_unit)}"""
    result = {
        canonical_name: units.convert(df[src_col], source_unit, canonical_unit)
        for src_col, (canonical_name, source_unit, canonical_unit) in column_spec.items()
    }
    return pd.DataFrame(result, index=df.index)


# run.metadata contract: every source provides exactly these keys, None if not applicable.
# Anything else a source wants to report goes in run.derived instead.
METADATA_FIELDS = (
    "run_id",
    "source",
    "mode",
    "date_time",
    "mean_wind_speed_ms",
    "mean_wind_direction_deg",
    "angle_of_attack_deg",
    "building_position_deg",
    "met_height_m",
    "sonic_height_m",
    "tower_heights_m",
)


def build_metadata(values: dict) -> dict:
    extra = set(values) - set(METADATA_FIELDS)
    if extra:
        raise ValueError(f"unexpected metadata fields: {sorted(extra)}")
    return {key: values.get(key) for key in METADATA_FIELDS}
