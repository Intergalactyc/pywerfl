# PyWERFL
Python library to aid in analysis of data from the [TTU Wind Engineering Research Field Laboratory (WERFL)](https://www.depts.ttu.edu/nwi/research/facilities/WERFL.php).

<INSTALL INSTRUCTIONS HERE>

## Data Access
### DesignSafe
Some data is publicly available in the [NSF NHERI DesignSafe project PRJ-1331](https://www.designsafe-ci.org/data/browser/public/designsafe.storage.published/PRJ-1331). As of August 2026, this project contains 16 runs of data in mode M1001, collected in 2003. To access this data, you first must create a TACC account. Go to the provided link, create an account, and note your username and password.

Once you have an account, you can download the data in several different ways. A simple method is using the secure copy protocol (SCP). From a terminal, run the following command:
```
scp -r yourusername@data.tacc.utexas.edu:/corral/projects/NHERI/published/published-data/PRJ-1331 desired/output/path
```
Make sure to update `yourusername` to reflect your TACC username, and change `desired/output/path` to the path on your computer where you'd like the downloaded dataset to go. You will be prompted to enter your account password, followed by a corresponding MFA code.

## Data Transformation

`pywerfl` supports multiple raw data sources, each with its own ingestion module under `pywerfl.sources`, all resulting in the same "analysis-ready" format.

For a DesignSafe PRJ-1331 download:
```bash
python -m pywerfl.sources.designsafe <raw_download_dir>
```

## Data Loading
Regardless of which source produced a given run, once it has been ingested into some directory

```python
from pywerfl import loader

run = loader.load_run("<analysis_ready_dir>", "1851")    # For example, to load run number 1851
run.cp                                                    # pressure coefficients, columns = tap IDs, indexed by elapsed_seconds
run.met, run.sonic, run.tower                             # meteorological / sonic / tower-anemometry data
run.metadata                                              # date, mean wind speed/direction, angle of attack, building position
```

## Some other notes and observations
- So far the loader's only made to work for DesignSafe; once I have other data to work with, I'll extend it
- Tap numbers are of the format SXXYY, where S is the surface (1=)
### DesignSafe
- At least here, there are some mislabeled taps in the "Cp File Structure" file; after some investigation of the naming structure and the unused taps in the "tap_locations" file, the correct values were identified. Corrections are made in `sources.designsafe_reference`, more details are included there in corresponding comments.
- The downloaded dataset has a lot of redundancy (identical files included several places in the directory, confirmed to be byte-for-byte the same via hashing). This is eliminated in the transformation step done by the ingestion module, and the total dataset size is reduced by a factor of ~5.