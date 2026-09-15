---
title: Scientific Results
status: canonical result interpretation
last_updated: 2026-09-15
paper_source: false
prose_reviewed: true
claim_ids: C-EIG-RAW-001, C-EIG-COST-001, C-FIXED-001, C-RECOVERY-001, C-ADEQ-001, C-MM3-GATE-001
---

# Scientific Results

| Contrast or result | Outcome | Evidence |
|---|---|---|
| Raw EIG vs predictive variance | Five measurements in all 30 pairs; tie | `E4` |
| Raw EIG vs Laplace D-optimality | Five measurements in all 30 pairs; tie | `E4` |
| EIG/cost vs predictive variance/cost | Mean -15.17 modeled-cost units; EIG loses all 30 | `E4`, `E5` |
| EIG/cost vs Laplace D-optimality/cost | Tie in all 30 | `E4` |
| Raw EIG vs deterministic fixed traversal | Five versus nine measurements | `E4` |
| Accepted measured permeability fits | Loss-component RRMSE 36.77%--52.42% | `E7` |
| SparseMix-1 endpoint-free diagnostic | `n3`: mixing supported; `n4`: mixing not supported | `E12` |
| MM-3 combined mismatch, raw EIG | Gate 30/30; false confidence 22/30 | `E16` |
| MM-3 EIG/cost vs predictive variance/cost | EIG/cost loses all 30 pairs in every scenario | `E16` |

The benchmark does not show EIG superiority over strong comparators. A
descriptive path analysis found that raw EIG ranked candidates almost
identically to predictive variance and Laplace D-optimality at exact shared
posterior states (mean Spearman correlations 0.9967 and 0.9947). For the
cost-normalized policies, the decisive third acquisition differed: EIG/cost
selected a 10 kHz inductance measurement in 28/30 seeds, while predictive
variance/cost selected the 500 kHz, 0.2 T core-loss point in 29/30 and crossed
the gate in every seed. This post hoc evidence supports objective--gate
misalignment within the matched-model benchmark; it is not a general ranking
of acquisition methods. [Source E9](../evidence/Evidence-Sources.md#e9)

Full trajectory interpretation remains in the
[job ledger](Scientific-Job-Results.md).

SparseMix-1 is a sampler diagnostic for the two rejected MM-2 states. Its
result does not supply model-mismatch performance evidence and does not change
MM-2 non-admission. [Source E12](../evidence/Evidence-Sources.md#e12)

## Model mismatch

MM-3 completed the exact preregistered 4-scenario × 30-seed matrix with all
eight policies and no numerical rejection. Raw EIG reached the local precision
gate in every seed of every scenario. False confidence increased from 0/30 in
the matched control to 9/30 under the two-pole permeability departure, 1/30
under temperature/curvature core-loss departure, and 22/30 under the combined
departure. [Source E16](../evidence/Evidence-Sources.md#e16)

The strong-policy count differences remained small. Raw EIG's mean advantage
over predictive variance was 0.067 measurements in the first three scenarios
and 0.10 in combined mismatch. Its advantage over Laplace D-optimality was
0.167 and 0.10, respectively. EIG/cost lost to predictive-variance/cost in
all 30 paired seeds in every scenario. The false-confidence result therefore
cannot be interpreted as evidence that EIG is uniquely responsible: the
other strong adaptive policies recorded 21--23 false-confident seeds under
combined mismatch. [Source E16](../evidence/Evidence-Sources.md#e16)

The admitted conclusion is narrower: the specified local posterior-width gate
can be satisfied while truth error and fixed latent-holdout performance remain
poor under the three locked structural departures. The experiment does not
test measured materials or arbitrary discrepancy families.
