"""Post-ingestion per-run summary statistics"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from pywerfl import circular, schema
from pywerfl.loader import Run

_DIRECTION_NAME = "wind_direction"
_SPEED_NAME = "wind_speed"


@dataclass
class RunSummary:
    run_id: str
    tables: dict[str, pd.DataFrame] = field(repr=False)

    def __getattr__(self, name: str) -> pd.DataFrame:
        try:
            return self.tables[name]
        except KeyError:
            raise AttributeError(
                f"RunSummary {self.run_id!r} has no table {name!r}; available: {sorted(self.tables)}"
            ) from None


def _paired_speed_column(name: str) -> str:
    if name == _DIRECTION_NAME:
        return _SPEED_NAME
    return name[: -len(_DIRECTION_NAME)] + _SPEED_NAME


def _scalar_stats(series: pd.Series) -> dict:
    return {
        "mean": series.mean(), "std": series.std(), "skew": series.skew(), "kurt": series.kurt(),
        "min": series.min(), "max": series.max(), "n": series.count(),
        "is_circular": False, "vector_mean": np.nan,
    }


def _direction_stats(direction: pd.Series, speed: pd.Series | None) -> dict:
    d = direction.dropna()
    stats = {
        "mean": circular.circular_mean(d) if len(d) else np.nan,
        "std": circular.circular_std(d) if len(d) else np.nan,
        "skew": circular.circular_skew(d) if len(d) else np.nan,
        "kurt": circular.circular_kurt(d) if len(d) else np.nan,
        "min": np.nan, "max": np.nan, "n": len(d), "is_circular": True,
    }
    if speed is not None:
        aligned = pd.concat([speed, direction], axis=1).dropna()
        stats["vector_mean"] = circular.vector_mean(aligned.iloc[:, 0], aligned.iloc[:, 1])[1] if len(aligned) else np.nan
    else:
        stats["vector_mean"] = np.nan
    return stats


def _summarize_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for name in df.columns:
        if schema.is_direction_column(name):
            speed_col = _paired_speed_column(name)
            speed = df[speed_col] if speed_col in df.columns else None
            rows[name] = _direction_stats(df[name], speed)
        else:
            rows[name] = _scalar_stats(df[name])
    return pd.DataFrame.from_dict(rows, orient="index")


def summarize_run(run: Run) -> RunSummary:
    return RunSummary(run_id=run.run_id, tables={name: _summarize_table(df) for name, df in run.tables.items()})
