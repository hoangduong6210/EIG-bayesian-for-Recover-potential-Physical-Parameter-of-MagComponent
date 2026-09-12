---
title: Sparse posterior sampler pilot
status: complete exploratory sampler comparison
last_updated: 2026-09-12
paper_source: false
---

# Sparse posterior sampler pilot

SparseMix-Pilot-1 compares numerical methods on the two posterior states
reconstructed in SparseMix-1. The unresolved four-measurement state motivates
the comparison. [Source E12](../evidence/Evidence-Sources.md#e12)

The executable design is
[`sparse_mixing_pilot.toml`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/configs/sparse_mixing_pilot.toml).
Its matrix crosses two states, three sampler arms, two initialization families,
and two replicates, for 24 tasks. Each task uses 48 walkers, 10,000 warmup
iterations and 80,000 retained iterations. Checkpoints are fixed at 20,000,
40,000, 60,000 and 80,000 retained iterations. All 24 tasks and 72 artifacts
passed the full-chain audit. [Source E13](../evidence/Evidence-Sources.md#e13)

## Sampling methods

| Arm | Proposal | Coordinates |
|---|---|---|
| `stretch` | Original stretch move | Original six active coordinates |
| `de_snooker` | Differential evolution with probability 0.8; snooker with probability 0.2 | Original six active coordinates |
| `logit_stretch` | Stretch move | Logit transformation of the bounded Cole--Cole exponent; other coordinates unchanged |

For the transformed arm, let
$\alpha_{\mathrm{cc}}=0.85\operatorname{sigmoid}(z)$. The sampled log density
includes $\log(0.85)-\log(1+e^{-z})-\log(1+e^z)$, the log absolute Jacobian.
Initialization is paired in the original coordinates. Both posterior density
implementations must agree before sampling. All autocorrelation estimates,
quantile comparisons and covariance summaries use the original six coordinates.

## Interpretation and continuation

The following values are worst cases over four independent ensembles per
state and method. Median and tail differences are normalized by the comparison
scales defined in the manifest; values above one exceed those scales.

| State | Method | Minimum steps/τ | Maximum relative τ change | Maximum median ratio | Maximum tail ratio |
|---|---|---:|---:|---:|---:|
| n3 | Stretch | 15.12 | 21.01% | 2.206 | 0.664 |
| n3 | DE + snooker | 108.30 | 5.44% | 0.103 | 0.081 |
| n3 | Logit stretch | 16.93 | 22.05% | 0.612 | 0.134 |
| n4 | Stretch | 11.10 | 26.23% | 1.151 | 0.493 |
| n4 | DE + snooker | 58.64 | 11.19% | 0.621 | 0.457 |
| n4 | Logit stretch | 12.33 | 28.16% | 0.945 | 0.270 |

[Table source E13](../evidence/Evidence-Sources.md#e13), `/method_summaries`.

DE + snooker is selected for the prospective study: it improves the worst-chain
autocorrelation measures in both states without a detected cross-ensemble
quantile disagreement. This is exploratory method selection, not a
preregistered comparison of sampler superiority. At n4 its 11.19% change in τ
still exceeds the 10% criterion proposed for the long run. Transforming only
the Cole--Cole exponent did not resolve the slow-mixing behavior.

Full retained chains and log probabilities are saved to permit recomputation
of the pilot diagnostics. No acquisition score, prediction error, truth
distance, coverage endpoint or policy contrast is computed. The locked MM-2
state reconstruction and observation hashes must match before any chain starts.

The pilot informs method selection for SparseMix-2. Low estimated
autocorrelation alone is insufficient: a short chain can miss slowly explored
tails. Selection examines both states, independent initializations, quantile
agreement and autocorrelation stability. Acceptance is reported separately
because its useful range depends on the proposal.

[SparseMix-2](Sparse-Mixing-V2-Preregistration.md) is registered after the
complete pilot inspection and before its fresh chains run. Its sampler,
seeds, horizon, diagnostics and failure rule are fixed at registration.
A new model-mismatch campaign
requires both locked states to pass that prospective rule. Gate-aligned
utility and simulation-based calibration follow the admitted mismatch study.
MM-1 and MM-2 retain their recorded non-admission.
