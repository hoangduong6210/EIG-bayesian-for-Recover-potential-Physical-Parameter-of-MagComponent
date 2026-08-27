---
title: Scientific Results
status: canonical result interpretation
last_updated: 2026-08-19
paper_source: true
prose_reviewed: true
claim_ids: C-EIG-RAW-001, C-EIG-COST-001, C-FIXED-001, C-RECOVERY-001, C-ADEQ-001
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

The benchmark does not show EIG superiority over strong comparators. A
descriptive path analysis found that raw EIG ranked candidates almost
identically to predictive variance and Laplace D-optimality at exact shared
posterior states (mean Spearman correlations 0.9967 and 0.9947). For the
cost-normalized policies, the decisive third acquisition differed: EIG/cost
selected a 10 kHz inductance measurement in 28/30 seeds, while predictive
variance/cost selected the 500 kHz, 0.2 T core-loss point in 29/30 and crossed
the gate in every seed. This post hoc evidence supports objective--gate
misalignment within the matched-model benchmark; it is not a general ranking
of acquisition methods. [Source E9](../Evidence-Sources.md#e9)

Full trajectory interpretation remains in the
[job ledger](../Scientific-Job-Results.md).
