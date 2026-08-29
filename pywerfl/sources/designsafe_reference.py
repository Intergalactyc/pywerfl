"""
Parse the DesignSafe WERFL reference workbooks (column dictionaries + tap coordinates)
into lookup tables for designsafe.py.

Provides two correction tables fixing mislabeled tap IDs.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pandas as pd

# "Cp File Structure" column number -> corrected tap ID.
# The sheet's own value at each of these columns doesn't match any tap in tap_locations.xlsx's Wall/Roof sheets.
# To make corrections the unused tap IDs were compared to the grid pattern matched by surrounding columns
CP_TAP_ID_CORRECTIONS: dict[int, str] = {
    36: "23504", # sheet lists 20504 (duplicate of column 54's 20504); 23504 sits unused in Wall2. Neighbors: 24004, 24008, 24013, <this>, 23508, 23513; 23504 better fits pattern than 20504.
    50: "21513", # sheet lists 21530 (not a real tap); 21513 sits unused in Wall1. Neighbor columns: 21504, 21508, <this>, 21004, 21008, 21013; 21513 fits the 4/8/13 y-coordinate pattern seen here and throughout the grid.
    122: "50340", # sheet lists 50240 (not a real tap); 50340 sits unused in Roof. Neighbor columns: 50045, 50345, 50545, 51045, 50040, <this>, 50540, 51040, 50035, 50335, 50535, 51035; 50340 fits the 0/3/5/10 x-coordinate pattern seen here and throughout the grid.
}

# Nominal tap ID used by "Cp File Structure" -> surveyed tap ID recorded in tap_locations.xlsx's Roof sheet for the same physical location.
# These roof-edge taps sit at the eave lines on either side of the building.
# Most of them have nominal Y=0, but surveyed Y-coordinates are ~0.54 ft, rounding up to 1;
# the last has nominal Y=45 but surveyed Y-coordinate ~44.46 ft, rounding down to 44.
# All of the nominal IDs here were not found in the Roof sheet, and each of the corresponding surveyed IDs were unused,
# so it plausibly seems to just be a mismatch in the naming convention; this fixes it.
ROOF_EDGE_ID_EQUIVALENCE: dict[str, str] = {
    "50000": "50001",
    "50300": "50301",
    "50500": "50501",
    "51000": "51001",
    "51500": "51501",
    "52000": "52001",
    "52500": "52501",
    "52800": "52801",
    "53000": "53001",
    "50045" : "50044"
}

# Clean up the sheet naming convention
_TAP_LOCATION_SHEETS = {
    "wall1": "Wall1",
    "wall2": "Wall 2",
    "wall3": "Wall 3",
    "wall4": "Wall 4",
    "roof": "Roof",
}


def _numbered_rows(ws) -> list[tuple[int, object]]:
    """
    Yield (column_number, value) for a 2-column 'Column | Name' reference sheet,
    skipping the header row and any blank rows.
    """
    rows = []
    for col_num, value in ws.iter_rows(min_row=2, max_col=2, values_only=True):
        if col_num is None:
            continue
        rows.append((int(col_num), value))
    return rows


def load_column_names(reference_dir: Path) -> dict[str, list[str]]:
    """
    Return {"met": [3 met variable names], "tower": [21 tower variable names], "sonic": [7 sonic variable names]},
    in file-column order, from column_structure.xlsx's Met/Tower/Bldg sheets.
    """
    wb = openpyxl.load_workbook(reference_dir / "column_structure.xlsx", read_only=True, data_only=True)
    return {
        "met": [str(name) for _, name in _numbered_rows(wb["Met File Structure"])],
        "tower": [str(name) for _, name in _numbered_rows(wb["Tower Anemometry File Structure"])],
        "sonic": [str(name) for _, name in _numbered_rows(wb["Bldg Anemometry File Str"])],
    }


def load_cp_tap_ids(reference_dir: Path) -> list[str]:
    """
    Return the 206 tap IDs for cp.csv's columns, in file-column order, with CP_TAP_ID_CORRECTIONS applied.
    Columns 1-2 are the reference-pressure channels (60001, 60002).
    """
    wb = openpyxl.load_workbook(reference_dir / "column_structure.xlsx", read_only=True, data_only=True)
    tap_ids = []
    for col_num, value in _numbered_rows(wb["Cp File Structure"]):
        tap_id = CP_TAP_ID_CORRECTIONS.get(col_num, str(int(value))) # type: ignore
        tap_ids.append(tap_id)
    return tap_ids


def load_tap_locations(reference_dir: Path) -> pd.DataFrame:
    """
    Return the 204 building taps' physical coordinates as a DataFrame with
    columns tap_id, x_ft, y_ft, surface, note.
    Read from tap_locations.xlsx's Wall1/Wall 2/Wall 3/Wall 4/Roof sheets
    (NOT "All Taps", which is a larger master list apparently spanning multiple configurations).
    
    Tap IDs are normalized to match "Cp File Structure"'s nominal convention via
    ROOF_EDGE_ID_EQUIVALENCE, so this table's tap_id values line up directly with load_cp_tap_ids()'s output.
    """
    wb = openpyxl.load_workbook(reference_dir / "tap_locations.xlsx", read_only=True, data_only=True)
    surveyed_to_nominal = {surveyed: nominal for nominal, surveyed in ROOF_EDGE_ID_EQUIVALENCE.items()}

    records = []
    for surface, sheet_name in _TAP_LOCATION_SHEETS.items():
        ws = wb[sheet_name]
        for row in ws.iter_rows(max_col=3, values_only=True):
            if not row or row[0] is None:
                continue
            surveyed_id = str(int(row[0])) # type: ignore
            x_ft, y_ft = row[1], row[2]
            if surveyed_id in surveyed_to_nominal:
                tap_id = surveyed_to_nominal[surveyed_id]
                note = f"renamed from surveyed ID {surveyed_id} (roof-edge Y=0 nominal/surveyed convention)"
            else:
                tap_id, note = surveyed_id, ""
            records.append({"tap_id": tap_id, "x_ft": x_ft, "y_ft": y_ft, "surface": surface, "note": note})

    return pd.DataFrame.from_records(records).sort_values("tap_id").reset_index(drop=True)
