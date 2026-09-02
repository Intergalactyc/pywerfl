#!/usr/bin/env python3
"""
Ingest a single-run, already-clean, headered-CSV WERFL dataset (e.g. R647) into
the shared analysis-ready format. No clean/ intermediate stage - assumes the source is
already flat and well-formed. (Based on and for the R647 individual dataset)

Usage:
    python -m pywerfl.sources.onerunsimple <run_dir> [workspace_dir] [--overwrite]

workspace_dir defaults to $PYWERFL_DATA_DIR, or ~/.pywerfl if that's unset.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import openpyxl
import pandas as pd

from pywerfl import overrides, schema, units, workspace, write_data

SOURCE_NAME = "onerunsimple"
RUN_ID_WIDTH = 4

_MET_HEIGHT_M = 3.9624
_SONIC_HEIGHT_M = 9.144

_TOWER_HEIGHT_RE = re.compile(r"^x(\d+)ft(WindSpeed|WindDirection|AlongWindComp|CrossWindComp|Vertical)$")
_TOWER_QUANTITIES = {
    "WindSpeed": "wind_speed",
    "WindDirection": "wind_direction",
    "AlongWindComp": "along_wind",
    "CrossWindComp": "cross_wind",
    "Vertical": "vertical",
}
_TOWER_EXTRAS = {
    "x13ft3CupMaster": "13ft_3cup_master_wind_speed",
    "x13ft3CupVaneAlongWindComponent": "13ft_3cup_vane_along_wind",
    "x13ft3CupVaneCrossWindComponent": "13ft_3cup_vane_cross_wind",
}


def find_one(parent: Path, pattern: str) -> Path:
    matches = sorted(parent.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No match for {pattern!r} under {parent}")
    if len(matches) > 1:
        raise RuntimeError(f"Multiple matches for {pattern!r} under {parent}: {matches}")
    return matches[0]


def discover_run_number(run_dir: Path) -> str:
    cp_path = find_one(run_dir, "R*Cp.csv")
    m = re.match(r"R(\d+)Cp\.csv$", cp_path.name)
    if not m:
        raise RuntimeError(f"Could not parse a run number from {cp_path.name!r}")
    return m.group(1)


def padded_run_id(run_id: str) -> str:
    return f"{int(run_id):0{RUN_ID_WIDTH}d}"


def _read_raw_csv(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.index = pd.Index(df.index / 30.0, name="elapsed_seconds")
    return df


def _met_spec(names: list[str]) -> dict[str, tuple[str, str, str]]:
    temp, rel_humidity, bar = names
    return {
        temp: ("temperature", "degF", "K"),
        rel_humidity: ("relative_humidity", "%", "fraction"),
        bar: ("barometric_pressure", "inHg", "kPa"),
    }


def _sonic_spec(names: list[str]) -> dict[str, tuple[str, str, str]]:
    north, west, speed, direction, along, cross, vertical = names
    return {
        north: ("north", "mph", "m/s"),
        west: ("west", "mph", "m/s"),
        speed: ("wind_speed", "mph", "m/s"),
        direction: ("wind_direction", "deg", "deg"),
        along: ("along_wind", "mph", "m/s"),
        cross: ("cross_wind", "mph", "m/s"),
        vertical: ("vertical", "mph", "m/s"),
    }


def _tower_spec(names: list[str]) -> dict[str, tuple[str, str, str]]:
    spec = {}
    for name in names:
        if name in _TOWER_EXTRAS:
            spec[name] = (_TOWER_EXTRAS[name], "mph", "m/s")
            continue
        m = _TOWER_HEIGHT_RE.match(name)
        if not m:
            raise ValueError(f"unrecognized tower column: {name!r}")
        height, quantity = m.groups()
        canonical = _TOWER_QUANTITIES[quantity]
        unit = "deg" if canonical == "wind_direction" else "mph"
        target = "deg" if canonical == "wind_direction" else "m/s"
        spec[name] = (f"{height}ft_{canonical}", unit, target)
    return spec


def _tower_heights_m(names: list[str]) -> dict[str, float]:
    heights_ft = sorted({int(m.group(1)) for name in names if (m := _TOWER_HEIGHT_RE.match(name))})
    return {f"{h}ft": units.convert(h, "ft", "m") for h in heights_ft}


def _load_flow_parameters(path: Path) -> dict:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    headers, values = list(ws.iter_rows(values_only=True))[:2]
    return dict(zip(headers, values))


def _load_run_metadata(flow_params_path: Path, run_id: str, tower_names: list[str]) -> tuple[dict, dict]:
    p = _load_flow_parameters(flow_params_path)
    metadata = schema.build_metadata({
        "run_id": run_id,
        "source": SOURCE_NAME,
        "angle_of_attack_deg": p["Angleofattack"],
        "mean_wind_speed_ms": units.convert(p["Ref.Velocity"], "mph", "m/s"),
        "mean_wind_direction_deg": p["Ref.Dir"],
        "met_height_m": _MET_HEIGHT_M,
        "sonic_height_m": _SONIC_HEIGHT_M,
        "tower_heights_m": _tower_heights_m(tower_names),
    })
    derived = {
        "reference_temperature_k": units.convert(p["Ref.Temp"], "degF", "K"),
        "reference_pressure_kpa": units.convert(p["Ref.BarPres"], "inHg", "kPa"),
        "reference_relative_humidity": units.convert(p["Ref.RelHumid"], "%", "fraction"),
        "air_density_kg_m3": units.convert(p["Ref.Rho"], "slug/ft3", "kg/m3"),
        "velocity_pressure_kpa": units.convert(p["Ref.VelPres"], "psf", "kPa"),
        "roughness_length_m": units.convert(p["FlowPara.ZoPro"], "ft", "m"),
        "shear_velocity_log_law_ms": units.convert(p["FlowPara.Ustar"], "mph", "m/s"),
        "log_law_r_squared": p["FlowPara.LogLaw.R2"],
        "power_law_alpha": 1 / p["FlowPara.Alpha"],  # source reports power-law index n = 1/alpha
        "power_law_index_raw": p["FlowPara.Alpha"],
        "power_law_r_squared": p["FlowPara.Power.R2"],
        "integral_length_scale_best_fit_m": units.convert(p["IntegralScale.Best.Fit"], "ft", "m"),
        "integral_length_scale_direct_m": units.convert(p["IntegralScale.Dir.Int"], "ft", "m"),
        "shear_velocity_ms": units.convert(p["ShearVelocity"], "mph", "m/s"), # not entirely sure what this is, as it disagrees with FlowPara.UStar
        "turbulence_intensity": p["TurInt"],
        "roughness_length_turbulence_m": units.convert(p["ZoTurb"], "ft", "m"),
    }
    return metadata, derived


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path, help="Directory with one run's R<N>*.csv files and flow-parameters workbook")
    parser.add_argument(
        "workspace", type=Path, nargs="?", default=None,
        help=f"Shared output directory (default: ${workspace.ENV_VAR} or {workspace.DEFAULT})",
    )
    parser.add_argument("--overwrite", action="store_true", help="Refresh this run if it already exists in the workspace")
    args = parser.parse_args()

    run_dir: Path = args.run_dir.resolve()
    if not run_dir.is_dir():
        parser.error(f"Run directory does not exist: {run_dir}")

    ws: Path = args.workspace.resolve() if args.workspace is not None else workspace.default_workspace()
    analysis_ready_dir = ws / "analysis_ready"

    run_number = discover_run_number(run_dir)
    padded_id = padded_run_id(run_number)
    print(f"Discovered run {run_number}")

    if (analysis_ready_dir / f"run_{padded_id}").exists() and not args.overwrite:
        parser.error(f"Run {padded_id} already exists in {ws} (use --overwrite to refresh it)")

    analysis_ready_dir.mkdir(parents=True, exist_ok=True)

    cp_raw = _read_raw_csv(find_one(run_dir, f"R{run_number}Cp.csv"))
    met_raw = _read_raw_csv(find_one(run_dir, f"R{run_number}Met.csv"))
    sonic_raw = _read_raw_csv(find_one(run_dir, f"R{run_number}Sonic.csv"))
    tower_raw = _read_raw_csv(find_one(run_dir, f"R{run_number}Tower.csv"))

    tables = {
        "cp": cp_raw.rename(columns=lambda c: c[1:]),
        "met": schema.build_table(met_raw, _met_spec(list(met_raw.columns))),
        "sonic": schema.build_table(sonic_raw, _sonic_spec(list(sonic_raw.columns))),
        "tower": schema.build_table(tower_raw, _tower_spec(list(tower_raw.columns))),
    }

    flow_params_path = find_one(run_dir, f"Run{run_number}*flow parameters.xlsx")
    metadata, derived = _load_run_metadata(flow_params_path, padded_id, list(tower_raw.columns))

    run_overrides = overrides.for_run(overrides.load(run_dir), padded_id)
    if run_overrides:
        metadata = schema.build_metadata({**metadata, **run_overrides})
        print(f"Applied metadata overrides: {run_overrides}")

    write_data.write_run(analysis_ready_dir, padded_id, tables, metadata, derived=derived)
    print(f"Wrote run {padded_id} to {analysis_ready_dir}")


if __name__ == "__main__":
    main()
