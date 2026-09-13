---
title: Evidence Sources
status: canonical evidence source map
last_updated: 2026-09-12
paper_source: false
---

# Evidence sources

Quantitative result statements in this wiki point either to the disclosure-safe
projection [`evidence/results.json`](results.json) or to a separately hashed
diagnostic named below. The projection is generated from the verified frozen
release; it contains aggregates and derived trajectory audits, not machine
paths, scheduler metadata, credentials, or raw measured curves.

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
- Public audit v2: [release assets](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/releases/tag/evidence-20260817-audit-v2)
  and [immutable asset descriptor](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/d9bd14b29b43207038af2cef4d5f14925dee9aef/results/audit/20260817T072230Z_401e3030fe13/asset.json).

<a id="e9"></a>
## E9 — Comparator selection-path diagnostic

- Artifact: [`aggregate_summary.json`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/cf753667c3ac120bd856f0a0f53913a6c5367db4/results/diagnostics/selection_overlap/20260817T072230Z_401e3030fe13/aggregate_summary.json)
- SHA-256: `cbdfc7f19a707ed9e58d3fb129ddcd314c1b75e1447eaa1ebdf88f75b07b6153`
- Supports: exact-state score-rank correlations, selected-set and ordered-path
  overlap, per-step candidate frequencies, and realized one-step movement
  toward the two-target gate.
- Source records: the 30 benchmark-v4 trajectories published in the
  [v2 public audit release](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/releases/tag/evidence-20260817-audit-v2).
- Interpretation: this diagnostic was specified after seeing the primary
  comparator result. It is descriptive evidence about the observed paths, not
  a preregistered causal or counterfactual contrast.

<a id="e10"></a>
## E10 — MM-1 non-admission record

- Artifact: [`non_admission.json`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/26bc699b66f0866b1ea16e09dc5ffa0d26ca6e81/results/diagnostics/model_mismatch/MM-1/20260827T045036Z_e4c674a6ff98/non_admission.json)
- SHA-256: `dba31b989debfe1729261a0fb42e07317069a97095b743c0d73237500e5a5207`
- Supports: the declared 120-task matrix closed with 119 validated result
  records and one failed task marker; the aggregate was not created and no
  confirmatory MM-1 claim is allowed.
- Disclosure boundary: the record contains result and marker hashes but no
  acquisition endpoint, holdout, error, coverage, or policy-comparison value.
  It establishes non-admission, not a model-mismatch outcome.

<a id="e11"></a>
## E11 — MM-2 non-admission record

- Artifact: [`non_admission.json`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/225fea17b14e13f4b2f1ddbd868a16ae64d866a0/results/diagnostics/model_mismatch/MM-2/20260829T041912Z_002a58340aa0/non_admission.json)
- SHA-256: `bf11358cbdb411532d2b3e9695d1e4c82585ba8751912ef98a495f8c334e6cb8`
- Supports: the independent 120-task matrix closed with 119 validated results,
  one failed task marker, and one bound sampler-rejection sidecar; the
  dependent aggregate was not created and no MM-2 endpoint claim is allowed.
- Rejection scope: `combined_mismatch_seed9123` failed because the
  `random_channel_balanced` posterior did not pass the locked convergence
  rule at two states. The closeout binds the full sidecar by SHA-256 but does
  not copy its state diagnostics.
- Disclosure boundary: no acquisition endpoint, holdout value, truth error,
  coverage statistic, measurement count to gate, modeled cost, or policy
  contrast is present. E11 establishes non-admission and identifies a sampler
  diagnostic target; it is not model-mismatch performance evidence.

<a id="e12"></a>
## E12 — SparseMix-1 endpoint-free sampler diagnostic

- Artifact: [`manifest.json`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/17b6205c6a15d4368e9a4d0e9b1e9139809861d9/results/diagnostics/sparse_mixing/SparseMix-1/20260831T054419Z_44edb519aa48/manifest.json)
- Manifest SHA-256: `9577a89b64207f17f241c52f68316eb2487a1ec31afbf3f9d77c45ea366e1a6e`
- Public record: [complete diagnostic release](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/releases/tag/sparsemix-1-20260831-audit-v1)
  and [`asset.json`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/f48a3c5fce47506be968f0c37535ad4ed308711d/results/diagnostics/sparse_mixing/SparseMix-1/20260831T054419Z_44edb519aa48/asset.json).
- Supports: the endpoint-free matrix contains 18 validated tasks and 36
  artifacts. Under the locked diagnostic thresholds, the three-measurement
  state is classified `mixing_supported`; the four-measurement state is
  classified `mixing_not_supported`.
- Interpretation: the first state is consistent with a finite-horizon failure
  at 320,000 retained steps that resolves in the tested 800,000-step
  ensembles. At the second state, every independent ensemble remains below 50
  retained steps per estimated autocorrelation time; two ensembles also fail
  the locked autocorrelation-stability threshold, and the maximum normalized
  cross-ensemble tail difference is 1.14248.
- Disclosure boundary: the release contains 18 task records and 18
  deterministic thinned chains, but not the full walker-by-iteration chains.
  The full-chain diagnostics therefore require a rerun for independent
  recomputation. E12 contains no acquisition endpoint and does not change the
  non-admission of MM-2.

<a id="e13"></a>
## E13 — Endpoint-free sampler pilot and exploratory selection

- Artifact: [`manifest.json`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/results/diagnostics/sparse_mixing/SparseMix-Pilot-1/20260912T054816Z_efbc1c2f169e/manifest.json)
- Manifest SHA-256: `8d2e1298941d413dd3cb849425613ac08218c9b8d81846168b5ebb90b4bb0b87`
- Selection: [`decision.json`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/results/diagnostics/sparse_mixing/SparseMix-Pilot-1/20260912T054816Z_efbc1c2f169e/decision.json)
- Decision SHA-256: `5914e90dcace7622052cfb658db139510005802faaac33fd0a9e3aaeab29d756`
- Source revision: `efbc1c2f169e4debf8541a78c6d115eeb2295284`;
  validator revision: `df06d7bed1de397cd25156b61c2a321fc174839d`.
- Pointers: `/matrix`, `/method_summaries`, `/tasks`, `/artifacts`,
  `/verification`. The record accounts for all 24 tasks and 72 artifacts.
  Every checkpoint autocorrelation estimate, ESS and final parameter summary
  was independently recomputed from the saved full chain.
- Interpretation: DE + snooker was selected after the complete exploratory
  comparison. Its n4 autocorrelation stability remains insufficient at the
  pilot horizon; selection does not admit a model-mismatch campaign.
- Availability: the public manifest includes per-ensemble diagnostics,
  quantile summaries and original artifact hashes. Full chains remain in the
  production archive and are not included in this repository projection.
  Acceptance histories were not retained, so acceptance is checked for
  consistency rather than independently recomputed. No scientific endpoint
  or retroactive MM-2 admission is supplied.

<a id="e14"></a>
## E14 — SparseMix-2 prospective sampler validation

- Artifact: [`manifest.json`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/results/diagnostics/sparse_mixing/SparseMix-2/20260912T060428Z_7a00dff3106f/manifest.json)
- SHA-256: `1f73174325341bd1638e5ac6f8c503ce75ee42022b0da42124799c766b14d1db`
- Source and validator revision: `7a00dff3106fa72027f243b94b7b512391b2548c`.
- Configuration SHA-256: `89ac040be89cc248088c5ed42288645717e792b9cf2113cf413298db8a41092c`.
- Pointers: `/matrix` accounts for 16 tasks and 48 artifacts;
  `/classifications/n3` and `/classifications/n4` each record eight passing
  ensembles; `/both_states_pass` is true. `/tasks` provides every final
  parameter diagnostic and quantile summary, while `/artifacts` binds the
  original result, full-chain and completion-marker hashes.
- Verification: full-chain autocorrelation, ESS and quantiles were recomputed.
  Acceptance histories were not retained; acceptance was range/consistency
  checked, not independently recomputed. The public manifest retains that
  distinction. Full unthinned arrays remain in the production archive and
  are not bundled into this repository projection.
- Interpretation: independent confirmation supports mixing at the two locked
  sparse states under the registered DE + snooker protocol. It does not
  establish calibration, laboratory performance, model-mismatch robustness
  or convergence at every possible posterior state. MM-1 and MM-2 remain
  non-admitted; a new mismatch campaign needs its own registration and checks.

<a id="e15"></a>
## E15 — Endpoint-free production integration check

- Artifact: [`sampler_check.json`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/results/diagnostics/sparse_mixing/production_integration/20260913_ee35ebd/sampler_check.json)
- SHA-256: `07fa4edcc02ec2dd6a795cb07cab85c5978906e5c93f4d96294c47637344eb60`.
- Source revision: `ee35ebdba11dbfae6a16e5d63fe87a47a8808ed2`.
- Pointers: `/all_checks_passed` is true. `/states` binds each locked state,
  technical check seed and full recorded diagnostic history. The production
  sampler reached its gate at 80,000 retained steps for n3 and 100,000 for n4.
- Scope: this is a two-state integration check of adaptive production
  inference, with no acquisition or mismatch endpoint. It is not the
  eight-ensemble SparseMix-2 confirmation, nor an MM-3 result. The record
  retains reported diagnostics, not full chains for independent recomputation.

## Verification rule

[`build.py`](../build.py) rejects the wiki if the projection hash, release ID,
release-manifest hash, artifact total, acquisition-record count, or source
labels differ from the declared contract. The exporter can reproduce the
projection from an independently obtained verified release:

```bash
python wiki/evidence/export_results.py \
  --release-dir <verified-release-directory> \
  --output wiki/evidence/results.json
python wiki/build.py check
```
