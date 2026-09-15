---
title: Model-mismatch campaign MM-3
status: complete and admitted under the preregistered numerical contract
last_updated: 2026-09-15
paper_source: false
---

# Model-mismatch campaign MM-3

SparseMix-2 supports DE + snooker sampling at both locked sparse states.
[Source E14](../evidence/Evidence-Sources.md#e14) supplies the full diagnostic
decision. MM-3 is a separate model-mismatch campaign. No MM-3 outcome has been
generated at registration. Its executable contract is
[`configs/model_mismatch_v3.toml`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/configs/model_mismatch_v3.toml),
SHA-256 `cf4496117e72e9f79b0770f4181ef0db32c0498096f089429aa4909adc00d2e0`.

## Question and scope

How do model discrepancy and acquisition policy jointly affect precision-gate
reach, held-out latent prediction and false confidence? The matched control
separates algorithm behavior within the inference family from behavior under
the three specified structural departures. This is a synthetic robustness
study, not a laboratory timing study or validation of an expanded physical
model. No new utility is tuned using MM-3 outcomes.

## Fixed task matrix and pairing

The successor retains the four generating scenarios, eight acquisition
policies, common candidate-indexed outcomes, latent holdout, local precision
gate and endpoint definitions from the
[MM-2 protocol](Model-Mismatch-V2-Preregistration.md). New seeds are
10100--10129, outside the development, MM-1 and MM-2 sets. This gives a planned
120 scenario--seed tasks. These are prospective design quantities, not results.

Every seed defines one prior-predictive parameter anchor shared across the
four scenarios. The prior center is independent of its realized value. Every
policy within a scenario--seed receives the same pre-generated outcome for
each candidate. Across scenarios, standardized noise is paired, while the
generating mean changes. The configuration's `mm3_confirmatory_seed_v1`
label names this independent seed set; deterministic posterior-state seeds
continue to use the existing observed-design-key mapping and new base seeds.

The policy registry contains raw EIG, EIG/cost, fixed channel-balanced,
random channel-balanced, raw predictive variance, predictive variance/cost,
raw Laplace D-optimality and Laplace D-optimality/cost. Fixed traversal is not
described as uniform random or optimal design. EIG uses the previously locked
estimator decision, SHA-256
`eb334ae2c188f12e7f544be71b6f0c40be15913ceec0df60e5bf9a9258ed82b6`.
[Estimator evidence E3](../evidence/Evidence-Sources.md#e3)

## Generating scenarios

| Scenario | Permeability departure | Core-loss departure |
|---|---|---|
| `matched_control` | One-pole Cole--Cole family | Isothermal Steinmetz family |
| `permeability_two_pole` | Second-pole fraction 0.25; relaxation multipliers 0.75 and 5; exponent offsets −0.05 and 0.18 | None |
| `core_loss_temperature_curvature` | None | Temperature log-slope 0.0035/°C; log-frequency curvature 0.08; frequency–flux interaction 0.05 |
| `combined_mismatch` | Second-pole fraction 0.35; relaxation multipliers 0.55 and 7; exponent offsets −0.10 and 0.25 | Temperature log-slope 0.0055/°C; curvature 0.14; interaction 0.10 |

All coefficients are locked design values from the configuration. Generating
functions are separate from the likelihood. Acquisition remains isothermal
at 25°C; latent validation extends to 25°C, 60°C and 100°C without exposing
the validation points to acquisition or stopping. Temperature extrapolation
error is therefore an evaluated limitation, not an inferred temperature law.

The scientific change is numerical inference. The prior and one-pole
inference model remain unchanged; the sampler does not acquire access to the
generating parameters or discrepancy terms. MM-1 and MM-2 remain non-admitted
and their endpoint records are not pooled with MM-3.

## Production inference contract

The implementation uses the same `emcee` 3.1.6 DE/snooker moves and
original-coordinate density as SparseMix-2. Each production posterior starts
48 walkers around the prior center, discards 80,000 warmup steps, and checks
the retained chain every 20,000 steps, up to 800,000 steps. Acceptance is
computed after warmup reset.

The numerical gate requires finite retained log probabilities, ESS of at
least 400 and at least 50 retained steps per estimated autocorrelation time
for every parameter, mean acceptance within [0.05, 0.80], and two consecutive
checkpoint changes in every autocorrelation estimate of at most 10%.
The denominator is the current checkpoint estimate. The earliest eligible
decision is therefore at 60,000 retained steps.

This adaptive single-ensemble production gate is not the eight-ensemble
comparison used in SparseMix-2. Qualification of the move family at two states
does not establish between-ensemble agreement at all subsequent states.
Each production record retains the checkpoint history and this distinction.

The endpoint-free production integration check passed at both locked states:
n3 stopped at 80,000 retained steps and n4 at 100,000. It used new technical
check seeds, not MM-3 outcomes. It verifies the adaptive implementation, not
an independent repetition of SparseMix-2's eight-ensemble decision.
[Source E15](../evidence/Evidence-Sources.md#e15)

## Endpoints and analysis

Each policy begins with the same two fixed measurements and may acquire at
most 25 points. The stopping targets are the latent posterior median and 90%
interval at core loss (100 kHz, 0.1 T, 25°C) and inductance (100 kHz, 25°C).
Precision requires interval half-widths relative to the median of at most
8% and 5%, respectively; it is not a future noisy-observation interval.

Report gate-reach and failure counts over all 30 seeds. Measurement count
and modeled acquisition cost are summarized only among seeds reaching the
gate, alongside the failure denominator. The modeled costs are not measured
laboratory durations. Report holdout relative RMSE and latent 90% interval
coverage by channel, with core loss additionally stratified by temperature.

False confidence means reaching the precision gate while the absolute
relative median error exceeds 8% at the core-loss target or 5% at the
inductance target. Report it over all seeds and conditionally among seeds
reaching the gate. A narrow but biased posterior can therefore be identified
without changing the stopping policy.

The four paired strong-comparator contrasts are raw EIG versus raw predictive
variance and raw Laplace D-optimality for measurement count, and EIG/cost
versus their cost-aware variants for modeled cost. Positive comparator-minus-
EIG differences favor EIG. Count/cost contrasts use pairs reaching the gate
under both policies and retain the paired denominator, wins, ties and losses.
The locked aggregator reports paired descriptive summaries and 95% bootstrap
intervals. These intervals are descriptive, not a multiplicity-adjusted
family-wide declaration of policy superiority.

## Reproducibility and resource limits

Posterior seeds remain functions of the exact observed-design identities.
A two-entry least-recently-used cache limits resident full-chain storage;
an evicted fit is recomputed using the same seed and ordered observations.
No posterior thinning or sample-bank replacement is introduced by the cache.
Cache reuse and runtime can differ without changing the deterministic
scientific calculation. Full production chains are used during computation;
their permanent public retention is not implied by this design.

The executable plan must bind the SparseMix-2 configuration and complete
passing manifest by SHA-256 and reject either an incomplete state matrix or
a nonpassing state. A failed production sampler gate retains an endpoint-free
rejection sidecar. An incomplete task matrix cannot produce an admitted
aggregate, and diagnostic failure cannot be relabeled as an infrastructure
retry to change its seed or sampling budget.

## Admission and retention

All 120 scenario--seed records must be present, uniquely identified and bound
to the same configuration, source, estimator and sampler-qualification
digests. Every posterior state must pass the production numerical gate. The
aggregate is scheduled only after the entire array succeeds and independently
checks the exact record matrix. No partial aggregate, seed replacement,
mixed-protocol pooling or retrospective MM-2 admission is allowed.

Admission does not trust a stored `valid=true` flag alone. It reconstructs
ESS and steps/τ from reported τ and retained length, checks the complete
checkpoint schedule, reconstructs successive relative changes and the
two-change stability streak, and verifies stopping at the first eligible
checkpoint. Sampler version, move constants and qualification hashes must
match. These are consistency checks on reported diagnostics, not independent
recomputation of autocorrelation or acceptance from permanently saved chains.

Task records retain observations by identity, acquisition trajectories,
candidate scores when applicable, checkpoint diagnostics, holdout point
records and endpoint values. Rejections are stored separately without
scientific endpoint values. Full walker-by-iteration production chains are
not automatically saved by this campaign; checkpoint records support audit
of the decision logic, but independent full-chain recomputation requires a
rerun. This differs from the full-chain SparseMix-2 production archive.

An infrastructure retry must preserve seed and configuration in a separately
identified attempt. A numerical diagnostic failure closes the campaign as
non-admitted; it is not an opportunity to retune its horizon or acceptance
criteria. Scheduler failure and missing output are reported as such, not
converted into an unfavorable policy endpoint.

## Before execution

The production sampler integration check and full test suite must pass on
compute nodes. The final executable configuration, immutable source revision
and this protocol must then be publicly committed before any MM-3 outcome is
generated. Gate-aligned utility and simulation-based calibration remain
deferred until a new mismatch campaign has an admitted result.

## Execution and retrieval

The campaign was submitted from public commit
`a75d737c9d5058798edc1508cb9ae7c961bc9544` after its full test suite and Wiki
check passed on a compute node and
[CI completed successfully](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/actions/runs/34743778898).
The run is `20260913T065150Z_a75d737c9d50`. Its
[registration record](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/results/diagnostics/model_mismatch/MM-3/20260913T065150Z_a75d737c9d50/registration.json)
binds the source, configuration, prerequisites and submitted job identities.
Its SHA-256 is
`09df403319d6ea8ca7f2793d3a1092e5fce633c5f137900cd9d794aff8d06971`;
the Wiki build checks that binding alongside the protocol configuration.

| Stage | Identifier | Status at submission | Expected output |
|---|---|---|---|
| Release checks | `7273241` | Completed successfully | Full tests and Wiki contract |
| Scenario--seed array | `7273251` | Completed successfully, 120 tasks | One validated record per scenario--seed |
| Aggregate | `7273252` | Completed successfully | Exact-matrix aggregate |

At submission this was an execution record, not a result table. No gate-reach,
error, coverage or policy contrast was inspected from partial output. The read-only watcher
separates task and aggregate failures and checks scheduler terminal states,
including out-of-memory, timeout and cancellation when a shell failure marker
is missing. Transient accounting absence is retried rather than reported as a
numerical rejection. It never launches replacements or changes admission.

<a id="result"></a>
## Completed campaign and admission

The array and dependent aggregate completed successfully. All 120 registered
scenario--seed records passed the stored diagnostic contract; the matrix has
four scenarios, 30 independent seeds per scenario and all eight policies.
There were no missing or duplicate records, sampler rejections, or gate
failures. The audit independently matched every production source hash and
reconstructed the complete scientific aggregate from the sanitized task
records. Aggregate SHA-256:
`03e8d81c48f3b5eb2c807a47b880972d3ea727b149788c2deffc35f1ac1d222d`.
[Evidence E16](../evidence/Evidence-Sources.md#e16)

The central robustness result is a separation between local precision and
truth accuracy. Raw EIG reached the local two-target width gate in all 30
combined-mismatch seeds, but met the preregistered false-confidence definition
in 22. Its mean latent-holdout RRMSE and 90% interval inclusion were 19.68% and
15.69% for core loss and 39.76% and 35.00% for loss permeability. At 100°C,
core-loss RRMSE was 30.55% and interval inclusion was zero. These are fixed
synthetic holdout summaries, not empirical calibration estimates.
[Evidence E16](../evidence/Evidence-Sources.md#e16)

Raw EIG retained only a small measurement-count advantage over the strong
comparators. In the matched, two-pole and temperature/curvature scenarios its
mean advantage was 0.067 measurements over predictive variance and 0.167 over
Laplace D-optimality; the corresponding win/tie/loss counts were 2/28/0 and
5/25/0. In combined mismatch both advantages were 0.10 measurements, with
3/27/0. EIG/cost lost to predictive-variance/cost in every seed: the mean
comparator-minus-EIG difference was −15.33 modeled-cost units in the first
three scenarios and −15.17 in combined mismatch. These bootstrap contrasts
are descriptive and not multiplicity-adjusted.
[Evidence E16](../evidence/Evidence-Sources.md#e16)

This admission establishes results only for the three locked discrepancy
families and their matched control. It does not show that EIG causes false
confidence, that a fixed traversal is generally safer, or that any comparator
is optimal. It also does not establish laboratory-time savings, global
six-parameter identification, or measured-data robustness.

<a id="progress-20260913t1219z"></a>
### Progress checkpoint — 13 September 2026, 12:19 UTC

The array has completed 20 of 120 tasks with successful scheduler exit codes
and corresponding result files; ten tasks are running and 90 remain pending.
No task-failure marker or sampler-rejection record is present. The aggregate
is still waiting on the array and does not exist. These are execution counts,
not a partial policy comparison or a campaign admission decision.

The [endpoint-free progress record](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/results/diagnostics/model_mismatch/MM-3/20260913T065150Z_a75d737c9d50/progress_20260913T1219Z.json)
contains the observation timestamp, scheduler accounting and hashes of all
20 result artifacts. SHA-256:
`3d3b9fb4e4556de16d0d8ffb33c3c7c70130b8f20b550ea1a61baa4e85a8c2bb`.
No endpoint values were inspected for this checkpoint. The next decision at
that time remained validation of the complete task matrix, not inspection of
interim policy performance. This checkpoint is retained as execution history;
the completed result above supersedes it as the current state.

The source is prepared from a clean public commit. Each task receives one
CPU for vectorized sampling and a 64 GB memory limit; up to ten tasks run
concurrently. These are resource allocations, not laboratory-time estimates.
The submission script verifies the source archive, predecessor closeout,
estimator decision and qualified sampler evidence before scheduling.

```bash
bash scripts/submit.sh --prepare-only
bash scripts/submit_model_mismatch_v3.sh \
  runs/<prepared-run> <estimator-decision.json> <MM-2-non-admission.json>
bash scripts/watch_model_mismatch_v3.sh runs/<prepared-run>
```

The [scientific job register](../results/Scientific-Job-Results.md) records the
completed run and the [project status](../status/Project-Status.md) states its
claim boundary. The Wiki is the current scientific source; document snapshots
are not rebuilt by this evidence release.
