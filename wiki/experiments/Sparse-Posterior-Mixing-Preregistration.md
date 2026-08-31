---
title: Sparse-Posterior Mixing Diagnostic SparseMix-1
status: preregistered before diagnostic chains
last_updated: 2026-08-31
paper_source: false
---

# Sparse-posterior mixing diagnostic SparseMix-1

SparseMix-1 tests why two posterior states failed the fixed convergence rule
in MM-2. It is an endpoint-free sampler diagnostic, not a model-mismatch
performance campaign. The machine-readable contract is
[`configs/sparse_mixing_v1.toml`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/configs/sparse_mixing_v1.toml).
Its preregistration SHA-256 is
`f3d531d08ac24968bcd47b781b153fb18187a2576db8e9f2f8af11ee5fc5ea8c`.
No SparseMix-1 chain had been run when this protocol was committed.

## Parent evidence and fixed targets

The protocol binds the immutable MM-2 source archive, configuration, failed
marker, rejection sidecar, and endpoint-blind closeout by SHA-256. It targets
only the two `random_channel_balanced` states named by that rejection:

| Target | Observations | State SHA-256 | Original MCMC seed |
|---|---:|---|---:|
| `n3` | 3 | `4ef1263722e4af3968932b0f38b7e10839f4474d5bc4604aed40f481b385ad64` | 2950378469 |
| `n4` | 4 | `c53fb8373ff54b01ce874bf363af024715348b6f898a059704a7e29ac43b4869` | 1017639342 |

Each job reconstructs the state from the locked MM-2 generator, candidate
library, policy seed namespace, and candidate-indexed outcomes. Before
sampling, it must reproduce the declared design identities, state hash, MCMC
seed, and observation manifest. It must not load a successful MM-2 result,
continue acquisition, rank a candidate, or evaluate a scientific endpoint.

## Run matrix

For each target, one exact replay uses the original seed, prior-center
initialization, 48 walkers, 4,000 burn steps, and 320,000 retained steps. This
arm checks reconstruction and numerical reproducibility of the rejected state;
it is not expected to repair the known failure.

Eight independent ensembles are then run per target:

- four use independent local prior-center initialization;
- four use independent overdispersed Latin-hypercube initialization from the
  bounded prior coordinates.

Independent ensembles use 80,000 fixed warm-up steps and 800,000 fixed
retained steps. Diagnostics are evaluated at 20k, 40k, 80k, 160k, 320k, 480k,
640k, and 800k. No chain stops early. Seeds are derived from the protocol ID,
state hash, initialization family, and replicate number. Interacting walkers
are not treated as independent chains, so ordinary walker-level
Gelman--Rubin statistics are not reported.

## Fixed diagnostics

Within each ensemble, the record contains finite-log-probability fraction,
acceptance, autocorrelation time, effective sample size, retained steps per
autocorrelation time, split-half quantile drift, bound-adjacent mass, and the
covariance geometry of the three magnetic coordinates. Between independent
ensembles, the validator compares marginal medians and tails, initialization
families, and the stability of autocorrelation estimates from 640k to 800k.

A target is classified as having supported mixing only if every independent
ensemble has finite log probability, acceptance in [0.20, 0.60], at least 50
retained steps per estimated autocorrelation time for every parameter, stable
autocorrelation estimates, and no material separation between independent
initialization families. Failure of any condition yields an unresolved or
initialization-sensitive classification; it does not trigger extra chains or
a changed threshold.

## Output and interpretation boundary

The public record contains checkpoint diagnostics, deterministic thinned
samples, chain-block hashes, and an exact-matrix validator manifest. Full
walker-by-iteration chains are not public artifacts. The validator rejects
partial, duplicate, hash-mismatched, or endpoint-bearing records.

SparseMix-1 may distinguish a slowly explored connected ridge from
initialization sensitivity, separated posterior regions, or persistent
nonstationarity. It cannot establish truth recovery, predictive accuracy,
uncertainty calibration, model adequacy, policy superiority, laboratory-time
savings, or model-mismatch robustness. Regardless of its outcome, MM-2 remains
non-admitted. [Parent closeout E11](../evidence/Evidence-Sources.md#e11)
