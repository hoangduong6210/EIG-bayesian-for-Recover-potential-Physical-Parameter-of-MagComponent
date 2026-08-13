# Data boundary

This directory contains metadata, not duplicated bulk raw data. `manifest.yaml`
declares the exact Magnetic inputs selected from the upstream `materialdatabase`
snapshot. `checksums.sha256` uses paths relative to this repository and is
intended for preflight verification.

Stage the upstream repository as `data/external/materialdatabase`, so that its
data directory is `data/external/materialdatabase/data`. Alternatively, set
`MAGCORE_DATA_ROOT` to the upstream `data` directory. The default staging path
is ignored by Git.

`raw/` is reserved for an optional verified staging area and must remain immutable. `processed/` is run-derived, disposable, and must not be cited as source data. A staged file is accepted only if its digest equals the manifest.

The manifest is limited to complex permeability and core-loss inputs.
