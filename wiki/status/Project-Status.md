---
title: Project Status
status: canonical current status
last_updated: 2026-09-15
paper_source: false
---

# Project Status

Status date: 2026-09-15.

The present research phase is closed with the admitted matched-model and
MM-3 results below. Closure fixes the evidence and its interpretation; it
does not establish laboratory savings, global identification, or calibrated
uncertainty under discrepancy. No successor experiment is admitted by this
closeout. The [research handoff](Research-Handoff.md) records the reading
order, reproduction boundary, and future-work decisions.

## Completed scientific work

- A 30-paired-seed, eight-policy acquisition benchmark is complete.
  [Source E1](../evidence/Evidence-Sources.md#e1)
- Every policy uses the same prior-predictive truth and the same pre-generated
  candidate-indexed outcomes within a seed. [Source E1](../evidence/Evidence-Sources.md#e1)
- The candidate library has 37 unique, isothermal designs and no
  temperature-only duplicates. [Source E1](../evidence/Evidence-Sources.md#e1)
- The nested EIG setting is qualified at 1200 outer draws, 400 inner draws,
  and 40 replicates, including doubled-budget sentinels and ten downstream
  endpoint checks. [Source E3](../evidence/Evidence-Sources.md#e3)
- All acquisition posterior states passed adaptive MCMC gates.
  [Source E1](../evidence/Evidence-Sources.md#e1)
- The final policy states include a disjoint 23-point latent holdout and
  six-parameter recovery records. [Sources E1](../evidence/Evidence-Sources.md#e1) and
  [E6](../evidence/Evidence-Sources.md#e6)
- The scientific freeze passed audit, aggregation, checksum verification, and
  figure generation.

Validated freeze: **20260817T072230Z_401e3030fe13**
Manifest SHA-256:
**85448a2c3c9db2db051c94543d8a336e7157d55289f10c1792e9c57d433812f7**

[Release source E8](../evidence/Evidence-Sources.md#e8)

## MM-1 closeout

The preregistered structural-mismatch array reached a terminal task matrix on
27 August 2026. Of 120 declared scenario--seed tasks, 119 produced validated
records and one, `permeability_two_pole_seed8108`, produced a nonzero failure
marker without a valid result. The aggregate was therefore not created. MM-1
is closed as a diagnostic campaign and supplies no endpoint or policy claim.
[Source E10](../evidence/Evidence-Sources.md#e10)

The failed marker does not identify the policy, posterior state, or individual
diagnostic threshold responsible for rejection. Those details are not
inferred from the 119 successful records. A new campaign must preserve
rejection diagnostics prospectively and use a separate campaign identity.

## MM-2 closeout

MM-2 used the independent seeds 9100--9129 and prospectively retained
state-level rejection diagnostics. Its 120-task matrix also closed with 119
validated records and one failure, `combined_mismatch_seed9123`. The rejection
occurred in `random_channel_balanced` at two sparse posterior states that did
not meet the minimum steps-per-autocorrelation-time rule at the 320,000-step
cap. No aggregate was created and no MM-2 outcome was admitted.
[Source E11](../evidence/Evidence-Sources.md#e11)

The endpoint-free SparseMix-1 study completed all 18 tasks and validated all
36 artifacts. The three-measurement state passes the locked mixing criteria at
800,000 retained steps, consistent with finite-horizon slow mixing at the old
320,000-step cap. The four-measurement state remains unresolved: all eight
independent ensembles fail the 50-steps-per-autocorrelation-time criterion,
two fail autocorrelation stability, and the cross-ensemble tail criterion also
fails. This diagnostic neither retroactively admits MM-2 nor supplies a
model-mismatch endpoint. [Source E12](../evidence/Evidence-Sources.md#e12)

## MM-3 completion

The [prospective protocol](../experiments/Model-Mismatch-V3-Preregistration.md)
fixed 30 new seeds, four generating scenarios, eight policies and the original
scientific endpoints. Run `20260913T065150Z_a75d737c9d50` completed all 120
tasks; array `7273251` and aggregate `7273252` both exited successfully. Every
stored sampler decision passed, and the exact registered matrix reconstructed
the published aggregate. The campaign is admitted under this numerical
contract. [Source E16](../evidence/Evidence-Sources.md#e16)

The earlier endpoint-free checkpoint at 20/120 remains in the protocol as
execution history. No partial endpoint was used to change the campaign. The
final public audit bundle contains all 120 sanitized records, acquisition
trajectories, candidate scores and sampler checkpoint histories. It does not
contain full walker-by-iteration chains. [Source E16](../evidence/Evidence-Sources.md#e16)

In combined mismatch, raw EIG reached the local precision gate in all 30 seeds
but was false-confident in 22. Its core-loss holdout mean RRMSE and latent 90%
interval inclusion were 19.68% and 15.69%; at 100°C they were 30.55% and 0%.
Loss-permeability holdout RRMSE and inclusion were 39.76% and 35.00%. This
supports a failure of the local width gate under the specified discrepancy,
not a general claim about every form of model mismatch.
[Source E16](../evidence/Evidence-Sources.md#e16)

## Primary direct contrasts

The difference is comparator minus EIG; positive values favor EIG.

| Contrast | Mean | 95% paired-bootstrap CI | EIG W/T/L | Gate failures |
|---|---:|---:|---:|---:|
| Raw EIG vs predictive variance, measurement count | 0.00 | [0.00, 0.00] | 0/30/0 | 0/0 |
| Raw EIG vs Laplace D-optimality, measurement count | 0.00 | [0.00, 0.00] | 0/30/0 | 0/0 |
| EIG/cost vs predictive variance/cost, modeled cost | -15.17 | [-15.50, -15.00] | 0/0/30 | 0/0 |
| EIG/cost vs Laplace D-optimality/cost, modeled cost | 0.00 | [0.00, 0.00] | 0/30/0 | 0/0 |

[Table source E4](../evidence/Evidence-Sources.md#e4)

The fixed traversal needed nine measurements in every seed; raw EIG needed
five, a 44.4% reduction relative to that specific traversal. Random
channel-balanced traversal averaged 7.8 measurements and ranged from 5 to 13.
[Source E4](../evidence/Evidence-Sources.md#e4)

This result is explained at the acquisition-state level in
[Why EIG did not beat the strong comparators](../results/Scientific-Job-Results.md#why-eig-did-not-beat-the-strong-comparators).

## Secondary endpoints

On the disjoint latent holdout, raw EIG mean RRMSE was 3.12% for core loss,
1.32% for storage permeability, 3.93% for loss permeability, and 1.20% for
magnetizing inductance. EIG/cost gave 3.15%, 0.95%, 2.78%, and 0.85%.
Comparable strong-policy results prevent interpreting these values as an EIG
advantage.
[Source E6](../evidence/Evidence-Sources.md#e6)

The final 90% intervals contained a mean 5.13 of six generating parameters for
both EIG objectives, but the scale parameter \(k\) remained difficult across
all policies. This is not global six-parameter identification.
[Source E6](../evidence/Evidence-Sources.md#e6)

## Measured-data adequacy

Accepted core-loss fits have in-sample RRMSE from 8.79% to 18.21%. Accepted
permeability fits have 6.89%--9.33% RRMSE for \(\mu'\), but
36.77%--52.42% for \(\mu''\). The large loss-component residual is direct
evidence that the one-pole Cole--Cole family is inadequate for those records.
[Source E7](../evidence/Evidence-Sources.md#e7)

## Evidence availability

The validated aggregate projection is available with its release and source
hashes. Public audit release v2 provides all 30 sanitized acquisition
trajectories and the estimator decision chain; its larger asset also includes
the twelve flattened posterior-sample matrices. Raw measured curves and
walker-by-iteration chains are outside that bundle. [Sources E8](../evidence/Evidence-Sources.md#e8)
and [E9](../evidence/Evidence-Sources.md#e9). The separate SparseMix-1 release
contains all 18 endpoint-free task records and all 18 deterministic thinned
chains. It omits full walker-by-iteration chains, so full-chain diagnostics
must be reproduced by rerunning the locked workflow. [Source E12](../evidence/Evidence-Sources.md#e12)

## Sampler qualification completed before MM-3

The [sampler pilot](../experiments/Sparse-Sampler-Pilot.md) completed 24 tasks
and a 72-artifact full-chain audit. DE + snooker was selected for SparseMix-2;
the pilot alone did not qualify it because its n4 autocorrelation-stability
check was insufficient. [Source E13](../evidence/Evidence-Sources.md#e13)

[SparseMix-2](../experiments/Sparse-Mixing-V2-Preregistration.md) completed all
16 fresh ensembles and a 48-artifact full-chain audit. Both n3 and n4 pass:
each has eight passing ensembles, with maximum relative autocorrelation-time
changes of 1.23% and 2.56%, respectively. This satisfied the prerequisite for
MM-3 registration; it did not itself admit a mismatch endpoint or qualify all
future posterior states. [Source E14](../evidence/Evidence-Sources.md#e14)

## Future work at phase closure

Gate-aligned utility and simulation-based calibration remain unregistered
and unrun. The following sequence is a research agenda, not a record of
completed results. Detailed entry and completion criteria are maintained in
the [handoff](Research-Handoff.md#future-work-register).

1. Keep MM-1 and MM-2 permanently separate and non-admitted.
2. Preserve MM-3, SparseMix-2 and their original criteria without post hoc
   retuning.
3. Preregister a gate-aligned utility as a new experiment, using MM-3 only to
   define the motivation and evaluation boundary.
4. Preregister simulation-based calibration under the matched generative
   model to test inference implementation. Separately preregister coverage
   and predictive checks under mismatch; these assess robustness, not the
   standard SBC rank-uniformity claim.
5. Controlled laboratory timing and multi-lot measurements before any
   real-world time-saving claim.
6. Stable measured-data acquisition ranking only after the forward model and
   observation model pass adequacy checks.
