# Result freezing and paper lock

## Mutable run phase

Each SLURM task writes into a unique run/task directory. A task is complete only when its expected artifacts validate and `SUCCESS.json` exists. Logs, configuration, environment, code revision, data hashes, seed, scheduler metadata, and diagnostics travel with the result.

## Freeze gate

The freeze job must verify:

- the full expected experiment/material/seed matrix;
- no duplicate logical tasks or unresolved failed attempts;
- JSON/CSV schemas and finite numerical values;
- mandatory SLURM provenance for every heavy artifact;
- consistent code, dependency, configuration, and input-data hashes;
- declared convergence diagnostics and explicit pass/fail scientific gates;
- no `.partial` files or path escapes.

The job then creates `results/frozen/<release-id>/` containing `manifest.json`, `checksums.sha256`, `metrics/`, `tables/`, `diagnostics/`, `provenance/`, and relevant logs. All files are hashed after creation.

## Immutability

A frozen release is append-prohibited. Never repair it in place. Any correction or rerun creates a new release ID and a documented supersession relation. `results/CURRENT` is a human convenience, not a data-selection API.

## Paper lock

`paper/current_state/results.lock.yaml` selects the release used for manuscript
inputs. It records the release ID and expected release-manifest digest.
Table/figure generation fails if the digest differs, the release is
`UNFROZEN`, or any artifact checksum fails.

Changing the lock requires rerunning generated tables, figures, the paper build, and the claim-to-evidence audit. Manually transcribed numerical tables are prohibited.
