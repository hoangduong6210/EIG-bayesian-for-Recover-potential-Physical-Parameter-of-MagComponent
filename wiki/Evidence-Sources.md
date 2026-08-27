---
title: Evidence Sources
status: detailed evidence annex
last_updated: 2026-08-19
paper_source: false
---

# Evidence sources

All quantitative result statements in this wiki point to the disclosure-safe
projection [`evidence/results.json`](evidence/results.json). The projection is
generated from the verified frozen release; it contains aggregates and derived
trajectory audits, not machine paths, scheduler metadata, credentials, or raw
measured curves.

Evidence release: `20260817T072230Z_401e3030fe13`  
Release-manifest SHA-256:
`85448a2c3c9db2db051c94543d8a336e7157d55289f10c1792e9c57d433812f7`  
Projection SHA-256:
`60036e144daf64ad8220377ff7eabc3dbba80afe33ff9c57e3b71ab95162a388`

The JSON pointer identifies the exact machine-readable record behind each
source label.

<a id="e1"></a>
## E1 — Campaign and artifact accounting

- Pointer: `/campaign` and `/scientific_jobs`
- Supports: task count, artifact count, record classes, job status, acquisition
  audit dimensions, and complete artifact accounting.
- Upstream binding: `/sources/result_manifest` records
  `tables/result_manifest.json` with SHA-256
  `699acf6e60502594e9b781b47260ff46f93a3bb22491e71d04416ff229035afd`.

<a id="e2"></a>
## E2 — Identifiability and matched-model recovery

- Pointer: `/results/fisher`, `/results/recovery`, and
  `/results/recovery_interval_inclusion_total`
- Supports: local Fisher rank and conditioning, recovery errors, and interval
  inclusion counts.

<a id="e3"></a>
## E3 — Nested-estimator qualification

- Pointer: `/results/estimator_validation`
- Supports: selected Monte Carlo setting, downstream endpoint stability, and
  validation decisions. Local provenance fields are deliberately excluded.

<a id="e4"></a>
## E4 — Paired policy endpoints and direct contrasts

- Pointer: `/results/policy_endpoints` and `/results/primary_contrasts`
- Supports: measurement count, modeled cost, paired bootstrap intervals,
  win/tie/loss counts, and failure-to-gate counts for the eight policies.

<a id="e5"></a>
## E5 — Acquisition trajectory audit

- Pointer: `/results/trajectory_analysis`
- Supports: selected sequences, selected-set overlap, intermediate gate state,
  and utilities at shared observed-data states. These quantities are rebuilt
  from all 30 paired acquisition records listed by
  `/sources/acquisition_record_set`.

<a id="e6"></a>
## E6 — Secondary synthetic endpoints

- Pointer: `/results/secondary_validation`
- Supports: aggregate 23-point latent-holdout RRMSE and coverage, plus mean
  six-parameter interval inclusion. Per-seed arrays are omitted from the public
  projection.

<a id="e7"></a>
## E7 — Measured-data adequacy

- Pointer: `/results/measured_core_loss`,
  `/results/measured_permeability`, and
  `/results/excluded_measured_permeability`
- Supports: accepted in-sample fit errors and names of excluded measured
  records. This is aggregate adequacy evidence, not a public reconstruction
  from raw measured curves.

<a id="e8"></a>
## E8 — Release integrity

- Pointer: `/release` and `/sources`
- Supports: release identifier, source artifact hashes, and the digest over the
  30 acquisition-record path/hash pairs. The production release remains
  separate because its operational provenance is not a public manuscript
input.

<a id="e9"></a>
## E9 — Comparator selection-path diagnostic

- Artifact: [`aggregate_summary.json`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/results/diagnostics/selection_overlap/20260817T072230Z_401e3030fe13/aggregate_summary.json)
- SHA-256: `cbdfc7f19a707ed9e58d3fb129ddcd314c1b75e1447eaa1ebdf88f75b07b6153`
- Supports: exact-state score-rank correlations, selected-set and ordered-path
  overlap, per-step candidate frequencies, and realized one-step movement
  toward the two-target gate.
- Source records: the 30 benchmark-v4 trajectories published in the
  [v2 public audit release](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/releases/tag/evidence-20260817-audit-v2).
- Interpretation: this diagnostic was specified after seeing the primary
  comparator result. It is descriptive evidence about the observed paths, not
  a preregistered causal or counterfactual contrast.

## Verification rule

[`build.py`](build.py) rejects the wiki if the projection hash, release ID,
release-manifest hash, artifact total, acquisition-record count, or source
labels differ from the declared contract. The exporter can reproduce the
projection from an independently obtained verified release:

```bash
python wiki/evidence/export_results.py \
  --release-dir <verified-release-directory> \
  --output wiki/evidence/results.json
python wiki/build.py check
```
