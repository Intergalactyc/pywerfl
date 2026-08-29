#!/usr/bin/env python3
"""
Ingest a raw DesignSafe WERFL PRJ-1331 download into the shared analysis-ready format.
2 steps are performed:
    1. Reorganize raw data into a clean, short-path CSV tree
    2. Label columns, apply tap-ID corrections, build time index, and write analysis-ready Parquet

Usage:
    python -m pywerfl.sources.designsafe <raw_source_dir> [workspace_dir] [--overwrite]

workspace_dir defaults to $PYWERFL_DATA_DIR, or ~/.pywerfl if that's unset.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl
import pandas as pd

from pywerfl import workspace, write_data
from pywerfl.sources import designsafe_reference as reference

SOURCE_NAME = "designsafe"
RUN_ID_WIDTH = 4
_EXCEL_EPOCH = datetime(1899, 12, 30)
_INTERNAL_REFERENCE_TAPS = ("60001", "60002")


# --- Step 1 functions ---

def find_one(parent: Path, pattern: str) -> Path:
    matches = sorted(parent.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No match for {pattern!r} under {parent}")
    if len(matches) > 1:
        raise RuntimeError(f"Multiple matches for {pattern!r} under {parent}: {matches}")
    return matches[0]


@dataclass
class TransformLog:
    copied: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def record_copy(self, src: Path, dst: Path) -> None:
        self.copied.append({"src": str(src), "dst": str(dst), "bytes": dst.stat().st_size})

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"WARNING: {message}", file=sys.stderr)


def locate_source_layout(source: Path) -> dict:
    analysis_root = find_one(source, "Analysis--*")
    experiment_root = find_one(source, "Experiment--*")
    model_config = find_one(experiment_root / "data", "Model-config--*")
    data_root = model_config / "data"

    return {
        "analysis_stats": analysis_root / "data",
        "publication_time_histories": find_one(data_root, "Publication Time Histories"),
        "time_histories": find_one(data_root, "Time Histories"),
        "building_drawings": find_one(data_root, "Building Drawings"),
        "file_structure": find_one(data_root, "File Structure"),
        "tap_locations": find_one(data_root, "Pressure Tap Locations"),
        "project_metadata": find_one(source, "*_metadata.json"),
    }


def discover_run_ids(publication_time_histories: Path) -> list[str]:
    run_ids = [
        p.name[len("Run"):]
        for p in sorted(publication_time_histories.iterdir())
        if p.is_dir() and p.name.startswith("Run")
    ]
    run_ids.sort(key=int)
    return run_ids


def padded_run_id(run_id: str) -> str:
    """
    Zero-pad a numeric run ID (e.g. "276" -> "0276").
    This is also the run_id passed to write_data.write_run(), and the value stored in metadata.json.
    """
    return f"{int(run_id):0{RUN_ID_WIDTH}d}"


def clean_run_dirname(run_id: str) -> str:
    """Folder name for this run under <clean_dir>/runs/ and <clean_dir>/raw/."""
    return f"run_{padded_run_id(run_id)}"


def copy_file(src: Path, dst: Path, log: TransformLog) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    log.record_copy(src, dst)


def clean_runs(layout: dict, run_ids: list[str], clean_dir: Path, log: TransformLog) -> None:
    pth = layout["publication_time_histories"]
    th = layout["time_histories"]
    stats_dir = layout["analysis_stats"]

    for run_id in run_ids:
        run_dir = clean_run_dirname(run_id)
        pub_run = pth / f"Run{run_id}"

        copy_file(pub_run / f"Run{run_id}Cp.csv", clean_dir / "runs" / run_dir / "cp.csv", log)
        copy_file(pub_run / f"Run{run_id}Met.csv", clean_dir / "runs" / run_dir / "met.csv", log)
        copy_file(pub_run / f"Run{run_id}Sonic.csv", clean_dir / "runs" / run_dir / "sonic.csv", log)
        copy_file(pub_run / f"Run{run_id}Tower.csv", clean_dir / "runs" / run_dir / "tower.csv", log)

        stats_src = stats_dir / f"Run{run_id}SummaryStatistics.xlsx"
        if stats_src.exists():
            copy_file(stats_src, clean_dir / "runs" / run_dir / "summary_statistics.xlsx", log)
        else:
            log.warn(f"Run {run_id}: missing summary statistics at {stats_src}")

        raw_tower_src = th / f"Run{run_id}" / f"Run{run_id}Anem Tower UVW.csv"
        if raw_tower_src.exists():
            copy_file(raw_tower_src, clean_dir / "raw" / run_dir / "tower_extended.csv", log)
        else:
            log.warn(f"Run {run_id}: missing raw extended-tower file at {raw_tower_src}")


def clean_reference(layout: dict, clean_dir: Path, log: TransformLog) -> None:
    ref = clean_dir / f"{SOURCE_NAME}_reference"
    copy_file(layout["project_metadata"], ref / "project_metadata.json", log)
    copy_file(find_one(layout["file_structure"], "*.xlsx"), ref / "column_structure.xlsx", log)
    copy_file(find_one(layout["tap_locations"], "*.xlsx"), ref / "tap_locations.xlsx", log)
    copy_file(find_one(layout["tap_locations"], "*.pdf"), ref / "tap_locations_drawing.pdf", log)
    copy_file(find_one(layout["building_drawings"], "*.pdf"), ref / "building_drawings.pdf", log)


# --- Step 2 functions ---

def _excel_serial_to_datetime(serial: float) -> datetime:
    return _EXCEL_EPOCH + timedelta(days=serial)


def _cp_column_names(reference_dir: Path) -> list[str]:
    tap_ids = reference.load_cp_tap_ids(reference_dir)
    return [f"internal_{t}" if t in _INTERNAL_REFERENCE_TAPS else t for t in tap_ids]


def _read_labeled_csv(csv_path: Path, column_names: list[str]) -> pd.DataFrame:
    df = pd.read_csv(csv_path, header=None, names=column_names)
    df.index = pd.Index(df.index / 30.0, name="elapsed_seconds")
    return df


def _load_run_metadata(stats_path: Path, run_id: str) -> dict:
    wb = openpyxl.load_workbook(stats_path, read_only=True, data_only=True)
    ws = wb["Summary"]
    fields = {}
    for label, value in ws.iter_rows(min_col=1, max_col=2, values_only=True):
        if label is None or value is None:
            continue
        fields[str(label).strip().rstrip(":")] = value

    wind_direction = fields.get("Mean Wind Direction")
    angle_of_attack = fields.get("Angle of Attack")
    building_position = fields.get("Building Position")
    if building_position is None and wind_direction is not None and angle_of_attack is not None:
        building_position = (wind_direction - angle_of_attack) % 360

    date_time = fields.get("Date & Time")
    if isinstance(date_time, (int, float)):
        date_time = _excel_serial_to_datetime(date_time)
    if isinstance(date_time, datetime):
        date_time = date_time.isoformat()

    return {
        "run_id": run_id,
        "source": SOURCE_NAME,
        "mode": fields.get("Mode"),
        "date_time": date_time,
        "mean_wind_speed_mph": fields.get("Mean Wind Speed"),
        "mean_wind_direction_deg": wind_direction,
        "angle_of_attack_deg": angle_of_attack,
        "building_position_deg": building_position,
    }


def transform_run(
    clean_dir: Path,
    analysis_ready_dir: Path,
    run_id: str,
    column_names: dict[str, list[str]],
    cp_columns: list[str],
) -> None:
    src_run = clean_dir / "runs" / clean_run_dirname(run_id)
    padded_id = padded_run_id(run_id)

    tables = {
        "cp": _read_labeled_csv(src_run / "cp.csv", cp_columns),
        "met": _read_labeled_csv(src_run / "met.csv", column_names["met"]),
        "sonic": _read_labeled_csv(src_run / "sonic.csv", column_names["sonic"]),
        "tower": _read_labeled_csv(src_run / "tower.csv", column_names["tower"]),
    }
    metadata = _load_run_metadata(src_run / "summary_statistics.xlsx", padded_id)
    write_data.write_run(analysis_ready_dir, padded_id, tables, metadata)


# --- CLI ---

def _existing_run_conflicts(run_ids: list[str], clean_dir: Path, analysis_ready_dir: Path) -> list[str]:
    conflicts = []
    for run_id in run_ids:
        padded_id = padded_run_id(run_id)
        clean_run_exists = (clean_dir / "runs" / clean_run_dirname(run_id)).exists()
        analysis_ready_run_exists = (analysis_ready_dir / f"run_{padded_id}").exists()
        if clean_run_exists or analysis_ready_run_exists:
            conflicts.append(padded_id)
    return conflicts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="Root of the raw downloaded PRJ-1331 dataset")
    parser.add_argument(
        "workspace", type=Path, nargs="?", default=None,
        help=f"Shared output directory (default: ${workspace.ENV_VAR} or {workspace.DEFAULT})",
    )
    parser.add_argument("--overwrite", action="store_true", help="Refresh this invocation's runs if they already exist in the workspace")
    args = parser.parse_args()

    source: Path = args.source.resolve()
    if not source.is_dir():
        parser.error(f"Source directory does not exist: {source}")

    ws: Path = args.workspace.resolve() if args.workspace is not None else workspace.default_workspace()
    clean_dir = ws / "clean"
    analysis_ready_dir = ws / "analysis_ready"

    layout = locate_source_layout(source)
    run_ids = discover_run_ids(layout["publication_time_histories"])
    print(f"Discovered {len(run_ids)} runs: {', '.join(run_ids)}")

    conflicts = _existing_run_conflicts(run_ids, clean_dir, analysis_ready_dir)
    if conflicts and not args.overwrite:
        parser.error(
            f"{len(conflicts)} run(s) already exist in {ws}: {', '.join(conflicts)} "
            "(use --overwrite to refresh them)"
        )

    clean_dir.mkdir(parents=True, exist_ok=True)
    analysis_ready_dir.mkdir(parents=True, exist_ok=True)

    # --- Step 1 ---
    log = TransformLog()
    clean_runs(layout, run_ids, clean_dir, log)
    clean_reference(layout, clean_dir, log)

    log_path = clean_dir / f"{SOURCE_NAME}_transform_log.json"
    log_path.write_text(json.dumps({
        "source": str(source),
        "output": str(clean_dir),
        "run_ids": run_ids,
        "files_copied": len(log.copied),
        "copied": log.copied,
        "warnings": log.warnings,
    }, indent=2))

    print(f"Cleaned structure: copied {len(log.copied)} files to {clean_dir} ({len(log.warnings)} warnings)")

    # --- Step 2 ---
    reference_dir = clean_dir / f"{SOURCE_NAME}_reference"
    column_names = reference.load_column_names(reference_dir)
    cp_columns = _cp_column_names(reference_dir)

    tap_locations = reference.load_tap_locations(reference_dir)
    tap_locations.to_csv(analysis_ready_dir / f"{SOURCE_NAME}_tap_locations.csv", index=False)

    print(f"Transforming {len(run_ids)} runs...")
    for run_id in run_ids:
        transform_run(clean_dir, analysis_ready_dir, run_id, column_names, cp_columns)

    print(f"\nDone. Wrote clean structure to {clean_dir}")
    print(f"Wrote {len(run_ids)} runs + {SOURCE_NAME}_tap_locations.csv to {analysis_ready_dir}")


if __name__ == "__main__":
    main()
