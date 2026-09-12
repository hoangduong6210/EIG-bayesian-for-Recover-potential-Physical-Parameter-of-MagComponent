---
title: Sparse-Posterior Mixing Diagnostic SparseMix-1
status: completed endpoint-free diagnostic record
last_updated: 2026-09-12
paper_source: false
---

# Sparse-posterior mixing diagnostic SparseMix-1

SparseMix-1 tests why two posterior states failed the fixed convergence rule
in MM-2. It is an endpoint-free sampler diagnostic, not a model-mismatch
performance campaign. The machine-readable contract is
[`configs/sparse_mixing_v1.toml`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/configs/sparse_mixing_v1.toml).
Its preregistration SHA-256 is
`88817e15908b2fd476f3c08efdf6ac080f8ba216b1643351bf7bf4217d7c9435`.
No SparseMix-1 chain had been run when this protocol was committed.

## Execution status

The immutable run `20260831T054419Z_44edb519aa48` was submitted from source
revision `44edb519aa48` after the reconstruction anchors and implementation
passed the repository test suite. Its matrix contains two exact replays and 16
independent ensembles, followed by one dependent validator job. All 18 tasks
completed, the validator accepted all 36 declared artifacts, and no failure
marker was produced. [Source E12](../evidence/Evidence-Sources.md#e12)

## Results

| Locked state | Independent ensembles | Classification | Decisive evidence |
|---|---:|---|---|
| Three measurements (`n3`) | 8 | `mixing_supported` | Every preregistered gate passed; maximum normalized median and tail differences were 0.50677 and 0.14398 |
| Four measurements (`n4`) | 8 | `mixing_not_supported` | All eight ensembles remained below 50 retained steps per estimated autocorrelation time; two also failed the 10% autocorrelation-stability gate; normalized tail difference reached 1.14248 |

The exact replays reproduce the two rejected MM-2 diagnostic states under the
original seeds. At `n3`, the original 320,000-step replay has a minimum of
37.17 retained steps per estimated autocorrelation time. The eight independent
ensembles pass the same threshold after 800,000 retained steps, with minima
from 71.38 to 87.17. This is evidence for finite-horizon slow mixing under the
tested sampler and initializations; it is not proof that the posterior has one
globally connected region.

At `n4`, acceptance and effective sample-size thresholds pass, but the
steps-per-autocorrelation-time range remains 33.50--47.18 after 800,000
retained steps. The tail separation is between individual independent
ensembles and does not establish initialization-family sensitivity or
separated modes. The defensible conclusion is persistent unresolved slow
exploration under the locked sampler and horizon. [Source E12](../evidence/Evidence-Sources.md#e12)

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

The validator committed before execution applies the median and tail limits to
every pair of independent ensembles, which is stricter than comparing only the
two initialization-family aggregates. The result above follows that executed
all-pair contract; no threshold was changed after the chains were observed.

## Output and interpretation boundary

The [public diagnostic release](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/releases/tag/sparsemix-1-20260831-audit-v1)
contains checkpoint diagnostics, 18 deterministic thinned samples, chain-block
hashes, and the exact-matrix validator manifest. Full walker-by-iteration
chains are not public artifacts, so the full-chain diagnostics cannot be
recomputed from the 1-in-200 thins alone. The repository verifier checks the
portable manifest, all 37 payload hashes, NPZ shapes and dtypes, task identity,
and disclosure scope. [Source E12](../evidence/Evidence-Sources.md#e12)

SparseMix-1 may distinguish a slowly explored connected ridge from
initialization sensitivity, separated posterior regions, or persistent
nonstationarity. It cannot establish truth recovery, predictive accuracy,
uncertainty calibration, model adequacy, policy superiority, laboratory-time
savings, or model-mismatch robustness. MM-2 remains non-admitted.
[Parent closeout E11](../evidence/Evidence-Sources.md#e11)
