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
- exactly 30 benchmark-v4 acquisition records with the preregistered eight-policy registry;
- one estimator-decision digest across all acquisition records;
- algebraic agreement between each policy result and every policy-vs-fixed paired endpoint;
- the fixed 23-point disjoint holdout grid (8 core-loss, 6 real-permeability,
  6 imaginary-permeability, and 3 inductance points);
- reconstruction of every holdout channel summary from persisted point rows;
- no `.partial` files or path escapes.

The job then creates `results/frozen/<release-id>/` containing `manifest.json`, `checksums.sha256`, `metrics/`, `tables/`, `diagnostics/`, `provenance/`, and relevant logs. All files are hashed after creation.

Submission snapshots exactly `git archive HEAD`, so Git history, virtual
environments, ignored data, caches, and local-only documents cannot enter the
source archive. Input checksums are resolved against the staged
`MAGCORE_DATA_ROOT`, including roots whose path contains spaces. The scheduler
partition defaults to `nextgen`, may be overridden with `MAGCORE_PARTITION`,
and is recorded and checked at preflight. This partition is operational
provenance, not a scientific endpoint.

Resolved Python distributions are captured with the Python standard-library
metadata API; provenance capture does not require the `pip` command or module.

## Immutability

A frozen release is append-prohibited. Never repair it in place. Any correction or rerun creates a new release ID and a documented supersession relation. `results/CURRENT` is a human convenience, not a data-selection API.

## Paper lock

`paper/current_state/results.lock.yaml` selects the release used for manuscript
inputs. It records the release ID and expected release-manifest digest.
Table/figure generation fails if the digest differs, the release is
`UNFROZEN`, or any artifact checksum fails.

Changing the lock requires rerunning generated tables, figures, the paper build, and the claim-to-evidence audit. Manually transcribed numerical tables are prohibited.

The production freeze intentionally retains machine and scheduler provenance
and is not a public artifact. Public release uses the allowlisted projection in
[`PUBLIC_AUDIT_BUNDLE.md`](PUBLIC_AUDIT_BUNDLE.md), which rewrites dependency
links, recalculates hashes, and rejects machine paths, scheduler fields,
credentials, internal phase labels, and automated-system provenance names.
