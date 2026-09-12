---
title: Sparse posterior sampler pilot
status: technical pilot specified before execution
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
40,000, 60,000 and 80,000 retained iterations. These are design quantities;
the pilot has not yet produced an outcome.

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

Full retained chains and log probabilities are saved to permit recomputation
of the pilot diagnostics. No acquisition score, prediction error, truth
distance, coverage endpoint or policy contrast is computed. The locked MM-2
state reconstruction and observation hashes must match before any chain starts.

The pilot informs method selection for SparseMix-2. Low estimated
autocorrelation alone is insufficient: a short chain can miss slowly explored
tails. Selection examines both states, independent initializations, quantile
agreement and autocorrelation stability. Acceptance is reported separately
because its useful range depends on the proposal.

SparseMix-2 will be registered after the complete pilot is inspected and
before its fresh chains run. Its sampler, seeds, horizon, diagnostics and
failure rule will be fixed at registration. A new model-mismatch campaign
requires both locked states to pass that prospective rule. Gate-aligned
utility and simulation-based calibration follow the admitted mismatch study.
MM-1 and MM-2 retain their recorded non-admission.
