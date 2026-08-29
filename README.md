# PyWERFL
Python library to aid in analysis of data from the [TTU Wind Engineering Research Field Laboratory (WERFL)](https://www.depts.ttu.edu/nwi/research/facilities/WERFL.php).

## Installation

From a clone of this repo:
```bash
pip install -e .
```
This installs the package with its dependencies, and a `pywerfl-designsafe` console command equivalent to `python -m pywerfl.sources.designsafe`.

## Data Access
### DesignSafe
Some data is publicly available in the [NSF NHERI DesignSafe project PRJ-1331](https://www.designsafe-ci.org/data/browser/public/designsafe.storage.published/PRJ-1331). As of August 2026, this project contains 16 runs of data in mode M1001, collected in 2003. To access this data, you first must create a TACC account. Go to the provided link, create an account, and note your username and password.

Once you have an account, you can download the data in several different ways. A simple method is using the secure copy protocol (SCP). From a terminal, run the following command:
```
scp -r yourusername@data.tacc.utexas.edu:/corral/projects/NHERI/published/published-data/PRJ-1331 desired/output/path
```
Make sure to update `yourusername` to reflect your TACC username, and change `desired/output/path` to the path on your computer where you'd like the downloaded dataset to go. You will be prompted to enter your account password, followed by a corresponding MFA code.

## Data Transformation

`pywerfl` supports multiple raw data sources, each with its own ingestion module under `pywerfl.sources`, all resulting in the same "analysis-ready" format. All sources write into the same shared workspace: by default `~/.pywerfl`; set the `PYWERFL_DATA_DIR` environment variable to use a different location instead, or pass an explicit workspace path as a second argument to override it for one call.

For a DesignSafe PRJ-1331 download:
```bash
python -m pywerfl.sources.designsafe <raw_download_dir> [workspace]     # writes to (a) `workspace`, if specified, or (b) $PYWERFL_DATA_DIR, if existing, or (c) ~/.pywerfl, default
```

## Data Loading
Regardless of which source produced a given run, and using the same default/override workspace resolution as ingestion:

```python
from pywerfl import loader

run = loader.load_run("1851")     # loads run number 1851 from ingested analysis-ready data
run.cp                            # pressure coefficients, columns = tap IDs, indexed by elapsed_seconds
run.met, run.sonic, run.tower     # meteorological / sonic / tower-anemometry data
run.metadata                      # date, mean wind speed/direction, angle of attack, building position

loader.load_run("1851", "<workspace>/analysis_ready")   # alternative: point at an explicit workspace
```

## Some other notes and observations
- So far the loader's only made to work for DesignSafe; once I have other data to work with, I'll extend it
- Tap numbers are of the format SXXYY, where S is the surface, XX is the x coordinate, YY is the y coordinate (coordinates in ft from origin, rounded to nearest integer)
    - Surface 1: "North" wall ("wall1") - short wall with door
        - Building-relative North (this just establishes building reference angle of 0 degrees)
    - Surface 2: "East" wall ("wall2") - long wall
    - Surface 3: "South" wall ("wall3") - short wall
    - Surface 4: "West" wall ("wall4") - long wall
    - Surface 5: Roof ("roof") - roof of the building
    - Surface 6: Internal reference-pressure channels, not building surface
        - Reference pressure measured in pit about halfway between met tower and building
- I've assumed run IDs are globally unique (so no collisions when combining sources into the same workspace)
### DesignSafe
- At least here, there are some mislabeled taps in the "Cp File Structure" file; after some investigation of the naming structure and the unused taps in the "tap_locations" file, the correct values were identified. Corrections are made in `sources.designsafe_reference`, more details are included there in corresponding comments.
- The downloaded dataset has a lot of redundancy (identical files included several places in the directory, confirmed to be byte-for-byte the same via hashing). This is eliminated in the transformation step done by the ingestion module, and the total dataset size is reduced by a factor of ~5.
