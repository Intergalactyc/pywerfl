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

### Manual metadata overrides

If a raw source is missing a `run.metadata` fact it just doesn't record (e.g. R647 has no `date_time` anywhere in its own files), or gets one wrong, put a `metadata_overrides.json` file directly in the raw source directory (the same directory passed to the ingestion CLI):

```json
{
  "647": {"date_time": "2003-06-15T12:00:00"}
}
```

Keyed by run ID; values are merged into that run's metadata on every ingestion. Unrecognized field names raise immediately.

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
run.derived                             # extra, source-specific fields

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

`summary.cp` additionally gets four record-extreme columns per tap, computed by functions in `pywerfl.extremes`: Lieblein BLUE (Best Linear Unbiased Estimator) Gumbel-distribution fit to 15 epoch extrema.
- `iso_blue_max`/`iso_blue_min`: non-exceedance P=0.80, extrapolated to a 60-minute reference period (ISO 4354 1-hour design peak convention)
- `exp_blue_max`/`exp_blue_min`: non-exceedance P=0.5704 (the probability at which a Gumbel variate equals the distribution's mean), extrapolated to the record's own actual duration
    - A more statistically stable estimate of the real pressure peak over this record than the raw observed `min`/`max` values

## Visualizing pressures over the building

`pywerfl.viz` plots Cp maps over the building's 5 faces (roof + 4 walls), laid out as an "exploded view": roof in the center, wall 1 (North) left, wall 2 (East) top, wall 3 (South) right, wall 4 (West) bottom. Tap physical coordinates (`pywerfl.reference_data`) are used for cubic interpolation onto a smooth per-face map (nearest-neighbor fill outside the tap convex hull). An arrow shows the mean 13 ft wind speed/direction, anchored at whichever roof corner the wind strikes, and an "N" indicator shows true North.

Note that in order to save an animated pressure map efficiently/to typical video formats (e.g. MP4), you will need [FFMPEG](https://ffmpeg.org/) installed and on your system PATH. Without this, only GIF formats can be output.

```python
from pywerfl import loader, viz

run = loader.load_run("1851")

viz.plot_pressure_map(run)                               # mean Cp, smooth interpolated map (default)
viz.plot_pressure_map(run, stat="exp_blue_min")          # any summarizer.cp column
viz.plot_pressure_map(run, time=123.4)                   # instantaneous snapshot, nearest sample
viz.plot_pressure_map(run, show_points=True)             # overlay the raw tap locations
viz.plot_pressure_map(run, interpolate=False)            # points only, no smooth map
viz.plot_pressure_map(run, percentile=(5, 95))           # tighter/looser color-scale percentile (default: 1st/99th of the plotted values)
viz.plot_pressure_map(run, cp_range=(-2, 1))             # or an explicit (vmin, vmax) instead of a percentile

anim = viz.animate_pressure_map(run, max_frames=200)     # instantaneous Cp animated over the run, one fixed colorbar (1st/99th percentile of the whole run, by default)
anim = viz.animate_pressure_map(run, percentile=(5, 95)) # same percentile/cp_range options as plot_pressure_map, but over the whole run
anim = viz.animate_pressure_map(run, cp_range=(-2, 1))
anim.save("run1851.mp4")                                 # or display inline via anim.to_jshtml()

viz.plot_tap_locations()                                 # reference tap IDs, same layout, no run/coloring needed
viz.plot_tap_locations(alternate_labels=False)           # every label above its point, instead of alternating
```

The wind-arrow and North-indicator angles are derived from the wall-numbering/AOA/building-position relationships (see the module docstring for the exact formulas), verified numerically against real run metadata: e.g. wind arrives from the direction of the windward wall's outward normal, `building_position_deg + 90*(wall_number-1)`.

## Cp tap data quality

Some taps have bad data for a given run (e.g. a stuck or glitching pressure sensor); `pywerfl.qc` helps find and exclude them.

**Manual exclusion list**: put a `tap_exclusions.json` file directly in the workspace root (a sibling of `analysis_ready/`, e.g. `~/.pywerfl/tap_exclusions.json` by default) - unlike `analysis_ready/`/`clean/` this isn't regenerable, so don't delete it along with those. Format:

```json
{
  "0647": ["50505", "53020]
}
```

`loader.load_run` NaNs out listed taps automatically (`exclude_taps=True` by default); pass `exclude_taps=False` to see the true raw signal.

**Finding candidates and reviewing them**:

```python
from pywerfl import loader, qc, viz

run = loader.load_run("0647", exclude_taps=False)     # raw, so nothing already excluded hides itself
candidates = qc.find_suspicious_taps(run)             # flags implausible |mean| or suspiciously few unique values
candidates                                            # mean/std/min/max/median/mad/n_unique/unique_frac/flags, worst first
viz.plot_tap_diagnostic(run, "50505")                 # side-by-side time series + histogram, stats in the title
```

`find_suspicious_taps`'s two heuristics (implausible magnitude, low unique-value count) are simple and imperfect. Always look at the actual signal with `plot_tap_diagnostic` before excluding: a real windward-corner tap under an oblique wind can legitimately show a large, unique-value-poor extreme, while a stuck sensor looks like near-zero variance around a physically implausible offset. The exclusion list is meant to be the manually reviewed+confirmed result. `find_suspicious_taps` only proposes candidates, it never writes to the list itself.

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
- When checking different sources for the BLUE coefficients, a transcription error was caught in NIST's bluecoeff.m (at n=15, a_2 = 0.119134 there vs. the correct 0.119314 used here).
    - Compared NIST source at https://www.itl.nist.gov/div898/winds/gumbel_blue/gumbblue.htm as well as an MIT-made source at github.com/kikocorreoso/scikit-extremes
    - Found error while cross-checking against sum(a)=1 and sum(b)=0 unbiasedness identities
- For run 647, taps 50505 and 21508 were flagged for low unique values. 50505 also has implausibly high readings (Cp stuck around ~5), excluding as bad; however, 21508 just has very low variance and otherwise looks realistic. Taps 50345 and 50045 also flagged for implausible magnitude, but signals look normal, just extra negative (they are at the windward corner, so it seems to be a real vortex suction effect).
    - After looking at series and animation, it looks like 53020 may also be malfunctioning, recommend exclusion. (Minimum Cp of 0.4, never negative, consistently significantly higher than neighbors)

### DesignSafe
- At least here, there are some mislabeled taps in the "Cp File Structure" file; after some investigation of the naming structure and the unused taps in the "tap_locations" file, the correct values were identified. Corrections are made in `sources.designsafe_reference`, more details are included there in corresponding comments.
- The downloaded dataset has a lot of redundancy (identical files included several places in the directory, confirmed to be byte-for-byte the same via hashing). This is eliminated in the transformation step done by the ingestion module, and the total dataset size is reduced by a factor of ~5.

### onerunsimple
- For single-run datasets already saved as flat, headered CSVs (e.g. R647) - no reference workbook or clean/ intermediate needed, so this source's ingestion is a single pass to analysis-ready format.
- `FlowPara.Alpha` is the power-law *index* n = 1/alpha, a convention used in some older literature; `power_law_alpha` (in `run.derived`) is computed as its reciprocal (R647 value of ~7.6 becomes ~0.132), with the untransformed source value kept as `power_law_index_raw`.
- `building_position_deg` isn't given directly by this source either, but it is automatically computed on ingestion as `(mean_wind_direction_deg - angle_of_attack_deg) % 360`.
- Unclear what ZoTurb and ShearVelocity are
    - ShearVelocity disagrees with FlowPara.Ustar
