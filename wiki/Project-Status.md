---
title: Project Status Compatibility Page
status: detailed status annex
last_updated: 2026-08-26
paper_source: false
---

# Project Status

Status date: 2026-08-26.

## Completed scientific work

- A 30-paired-seed, eight-policy acquisition benchmark is complete.
  [Source E1](Evidence-Sources.md#e1)
- Every policy uses the same prior-predictive truth and the same pre-generated
  candidate-indexed outcomes within a seed.
- The candidate library has 37 unique, isothermal designs and no
  temperature-only duplicates. [Source E1](Evidence-Sources.md#e1)
- The nested EIG setting is qualified at 1200 outer draws, 400 inner draws,
  and 40 replicates, including doubled-budget sentinels and ten downstream
  endpoint checks. [Source E3](Evidence-Sources.md#e3)
- All acquisition posterior states passed adaptive MCMC gates.
  [Source E1](Evidence-Sources.md#e1)
- The final policy states include a disjoint 23-point latent holdout and
  six-parameter recovery records. [Sources E1](Evidence-Sources.md#e1) and
  [E6](Evidence-Sources.md#e6)
- The scientific freeze passed audit, aggregation, checksum verification, and
  figure generation.

Validated freeze: **20260817T072230Z_401e3030fe13**  
Manifest SHA-256:
**85448a2c3c9db2db051c94543d8a336e7157d55289f10c1792e9c57d433812f7**

[Release source E8](Evidence-Sources.md#e8)

## Primary direct contrasts

The difference is comparator minus EIG; positive values favor EIG.

| Contrast | Mean | 95% paired-bootstrap CI | EIG W/T/L | Gate failures |
|---|---:|---:|---:|---:|
| Raw EIG vs predictive variance, measurement count | 0.00 | [0.00, 0.00] | 0/30/0 | 0/0 |
| Raw EIG vs Laplace D-optimality, measurement count | 0.00 | [0.00, 0.00] | 0/30/0 | 0/0 |
| EIG/cost vs predictive variance/cost, modeled cost | -15.17 | [-15.50, -15.00] | 0/0/30 | 0/0 |
| EIG/cost vs Laplace D-optimality/cost, modeled cost | 0.00 | [0.00, 0.00] | 0/30/0 | 0/0 |

[Table source E4](Evidence-Sources.md#e4)

The fixed traversal needed nine measurements in every seed; raw EIG needed
five, a 44.4% reduction relative to that specific traversal. Random
channel-balanced traversal averaged 7.8 measurements and ranged from 5 to 13.
[Source E4](Evidence-Sources.md#e4)

This result is explained at the acquisition-state level in
[Why EIG did not beat the strong comparators](Scientific-Job-Results.md#why-eig-did-not-beat-the-strong-comparators).

## Secondary endpoints

On the disjoint latent holdout, raw EIG mean RRMSE was 3.12% for core loss,
1.32% for storage permeability, 3.93% for loss permeability, and 1.20% for
magnetizing inductance. EIG/cost gave 3.15%, 0.95%, 2.78%, and 0.85%.
Comparable strong-policy results prevent interpreting these values as an EIG
advantage.
[Source E6](Evidence-Sources.md#e6)

The final 90% intervals contained a mean 5.13 of six generating parameters for
both EIG objectives, but the scale parameter \(k\) remained difficult across
all policies. This is not global six-parameter identification.
[Source E6](Evidence-Sources.md#e6)

## Measured-data adequacy

Accepted core-loss fits have in-sample RRMSE from 8.79% to 18.21%. Accepted
permeability fits have 6.89%--9.33% RRMSE for \(\mu'\), but
36.77%--52.42% for \(\mu''\). The large loss-component residual is direct
evidence that the one-pole Cole--Cole family is inadequate for those records.
[Source E7](Evidence-Sources.md#e7)

## Evidence availability

The validated aggregate projection is available with its release and source
hashes. Public audit release v2 provides all 30 sanitized acquisition
trajectories and the estimator decision chain; its larger asset also includes
the twelve flattened posterior-sample matrices. Raw measured curves and
walker-by-iteration chains are outside that bundle. [Sources E8](Evidence-Sources.md#e8)
and [E9](Evidence-Sources.md#e9)

## Next scientific experiments

1. Run preregistered model-mismatch campaign MM-1: four fixed scenarios and 30
   new seeds. No MM-1 result has been admitted yet.
2. Preregister a gate-aligned utility after MM-1 is complete.
3. Run larger simulation-based calibration for parameter and predictive
   coverage.
4. Controlled laboratory timing and multi-lot measurements before any
   real-world time-saving claim.
5. Stable measured-data acquisition ranking only after the forward model and
   observation model pass adequacy checks.
