# PyWERFL
Python library to aid in analysis of data from the [TTU Wind Engineering Research Field Laboratory (WERFL)](https://www.depts.ttu.edu/nwi/research/facilities/WERFL.php).

## Installation

From a clone of this repo:
```bash
pip install -e .
```
This installs the package with its dependencies, and `pywerfl-designsafe`/`pywerfl-onerunsimple` console commands equivalent to `python -m pywerfl.sources.designsafe`/`python -m pywerfl.sources.onerunsimple`.

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

For a DesignSafe project download (e.g. PRJ-1331):
```bash
python -m pywerfl.sources.designsafe <raw_download_dir> [workspace]     # writes to (a) `workspace`, if specified, or (b) $PYWERFL_DATA_DIR, if existing, or (c) ~/.pywerfl, default
```

For a single-run, already-flat, headered-CSV dataset (e.g. R647):
```bash
python -m pywerfl.sources.onerunsimple <run_dir> [workspace]
```

### Unit and naming convention

Every source converts its own raw units into a fixed SI-based set on ingestion, via `pywerfl.units`/`pywerfl.schema`: wind speeds in m/s, temperatures in K, pressures in kPa, lengths in m, angles in degrees, relative humidity and turbulence intensity as a fraction (0-1), Cp and related quantities dimensionless. Column names carry no unit suffix (the unit is always whatever's listed above) and are the same across sources for the same measurement. A table or tap may simply be absent for a source/run that doesn't measure it. met/sonic instrument height and tower's per-height mapping live in `run.metadata` (`met_height_m`, `sonic_height_m`, `tower_heights_m`) rather than in column names, since met/sonic are each a single location per table.

`run.metadata` itself is a fixed contract, set in `pywerfl.schema.METADATA_FIELDS`: every source provides exactly the same set of keys, `None` for anything that doesn't apply. Anything extra a source wants to report goes in `run.derived` instead, which has no fixed key set and can be empty.

## Data Loading
Regardless of which source produced a given run, and using the same default/override workspace resolution as ingestion:

```python
from pywerfl import loader

run = loader.load_run("1851")           # loads run number 1851 from ingested analysis-ready data

# Example data access:
run.cp                                  # pressure coefficients, columns = tap IDs, indexed by elapsed_seconds
run.met, run.sonic, run.tower           # meteorological / sonic / tower-anemometry data
run.met.temperature                     # K
run.sonic.wind_speed                    # m/s
run.tower["13ft_wind_speed"]            # m/s
run.metadata                            # mean wind speed/direction, angle of attack, instrument heights, ... (same keys for every source)
run.derived                             # extra, source-specific fields (e.g. onerunsimple's boundary-layer flow parameters); {} if none

loader.load_run("1851", "<workspace>/analysis_ready")   # alternative: point at an explicit workspace
```

The function `loader.load_run` loads the run from the workspace (so long as it has been ingested there) as a `Run` object.

## Summarizing a run

`pywerfl.summarizer.summarize_run(run)` computes summary statistics (mean/std/skew/kurt/min/max/n) for every variable in `met`/`sonic`/`tower`/`cp`:

```python
from pywerfl import loader, summarizer

run = loader.load_run("1851")
summary = summarizer.summarize_run(run)

summary.sonic.loc["wind_speed"]          # mean, std, skew, kurt, min, max, n
summary.cp.loc["13004"]                  # same, per pressure tap
```

The function `summarizer.summarize_run` takes a `Run` object and returns a `RunSummary` object.

Wind-direction columns are detected automatically and get proper circular statistics. For these rows, `mean`/`std`/`skew`/`kurt` are all computed via `pywerfl.circular`, `min`/`max` are `NaN`, and an extra `vector_mean` column holds the speed-weighted true vector-average direction (paired from the matching `*_wind_speed` column, `NaN` if none exists). A helper column `is_circular` is provided to track which rows got this treatment.

## Some other notes and observations
- Tap coordinates (`pywerfl.reference_data`) are fixed and bundled with the
  package; which taps are actually instrumented (i.e. present as columns) can still vary by source/run
- Tap numbers are of the format SXXYY, where S is the surface, XX is the x coordinate, YY is the y coordinate (coordinates in ft from origin, rounded to nearest integer)
    - Surface 1: "North" wall ("wall1") - short wall with door
        - Building-relative North (this just establishes building reference angle of 0 degrees)
    - Surface 2: "East" wall ("wall2") - long wall
    - Surface 3: "South" wall ("wall3") - short wall
    - Surface 4: "West" wall ("wall4") - long wall
    - Surface 5: Roof ("roof") - roof of the building
    - Surface 6: Reference-pressure channels, not building surface
        - Reference pressure measured in pit about halfway between met tower and building
- I've assumed run IDs are globally unique (so there should be no collisions when combining sources into the same workspace)

### DesignSafe
- At least here, there are some mislabeled taps in the "Cp File Structure" file; after some investigation of the naming structure and the unused taps in the "tap_locations" file, the correct values were identified. Corrections are made in `sources.designsafe_reference`, more details are included there in corresponding comments.
- The downloaded dataset has a lot of redundancy (identical files included several places in the directory, confirmed to be byte-for-byte the same via hashing). This is eliminated in the transformation step done by the ingestion module, and the total dataset size is reduced by a factor of ~5.

### onerunsimple
- For single-run datasets already saved as flat, headered CSVs (e.g. R647) - no reference workbook or clean/ intermediate needed, so this source's ingestion is a single pass to analysis-ready format.
- `FlowPara.Alpha` is the power-law *index* n = 1/alpha, a convention used in some older literature; `power_law_alpha` (in `run.derived`) is computed as its reciprocal (R647 value of ~7.6 becomes ~0.132), with the untransformed source value kept as `power_law_index_raw`.
- Unclear what ZoTurb and ShearVelocity are
    - ShearVelocity disagrees with FlowPara.Ustar
