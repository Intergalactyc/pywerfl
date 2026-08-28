#!/usr/bin/env python3
"""
Transform a raw DesignSafe WERFL PRJ-1331 download into a clean structure.

Usage:
    python scripts/transform_dataset.py <source_dir> <output_dir> [--overwrite]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

RUN_ID_WIDTH = 4


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


def run_dirname(run_id: str) -> str:
    return f"run_{int(run_id):0{RUN_ID_WIDTH}d}"


def copy_file(src: Path, dst: Path, log: TransformLog) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    log.record_copy(src, dst)


def transform_runs(layout: dict, run_ids: list[str], output: Path, log: TransformLog) -> None:
    pth = layout["publication_time_histories"]
    th = layout["time_histories"]
    stats_dir = layout["analysis_stats"]

    for run_id in run_ids:
        run_dir = run_dirname(run_id)
        pub_run = pth / f"Run{run_id}"

        copy_file(pub_run / f"Run{run_id}Cp.csv", output / "runs" / run_dir / "cp.csv", log)
        copy_file(pub_run / f"Run{run_id}Met.csv", output / "runs" / run_dir / "met.csv", log)
        copy_file(pub_run / f"Run{run_id}Sonic.csv", output / "runs" / run_dir / "sonic.csv", log)
        copy_file(pub_run / f"Run{run_id}Tower.csv", output / "runs" / run_dir / "tower.csv", log)

        stats_src = stats_dir / f"Run{run_id}SummaryStatistics.xlsx"
        if stats_src.exists():
            copy_file(stats_src, output / "runs" / run_dir / "summary_statistics.xlsx", log)
        else:
            log.warn(f"Run {run_id}: missing summary statistics at {stats_src}")

        raw_tower_src = th / f"Run{run_id}" / f"Run{run_id}Anem Tower UVW.csv"
        if raw_tower_src.exists():
            copy_file(raw_tower_src, output / "raw" / run_dir / "tower_extended.csv", log)
        else:
            log.warn(f"Run {run_id}: missing raw extended-tower file at {raw_tower_src}")


def transform_reference(layout: dict, output: Path, log: TransformLog) -> None:
    ref = output / "reference"
    copy_file(layout["project_metadata"], ref / "project_metadata.json", log)
    copy_file(find_one(layout["file_structure"], "*.xlsx"), ref / "column_structure.xlsx", log)
    copy_file(find_one(layout["tap_locations"], "*.xlsx"), ref / "tap_locations.xlsx", log)
    copy_file(find_one(layout["tap_locations"], "*.pdf"), ref / "tap_locations_drawing.pdf", log)
    copy_file(find_one(layout["building_drawings"], "*.pdf"), ref / "building_drawings.pdf", log)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="Root of the downloaded PRJ-1331 dataset")
    parser.add_argument("output", type=Path, help="Directory to write the cleaned structure into")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output directory")
    args = parser.parse_args()

    source: Path = args.source.resolve()
    output: Path = args.output.resolve()

    if not source.is_dir():
        parser.error(f"Source directory does not exist: {source}")

    if output.exists():
        if not args.overwrite:
            parser.error(f"Output directory already exists: {output} (use --overwrite to refresh it)")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    log = TransformLog()

    layout = locate_source_layout(source)
    run_ids = discover_run_ids(layout["publication_time_histories"])
    print(f"Discovered {len(run_ids)} runs: {', '.join(run_ids)}")

    transform_runs(layout, run_ids, output, log)
    transform_reference(layout, output, log)

    log_path = output / "transform_log.json"
    log_path.write_text(json.dumps({
        "source": str(source),
        "output": str(output),
        "run_ids": run_ids,
        "files_copied": len(log.copied),
        "copied": log.copied,
        "warnings": log.warnings,
    }, indent=2))

    print(f"\nDone. Copied {len(log.copied)} files to {output}")
    print(f"Warnings: {len(log.warnings)}")
    print(f"Transform log written to {log_path}")


if __name__ == "__main__":
    main()
