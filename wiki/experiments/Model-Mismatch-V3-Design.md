---
title: MM-3 design after sparse-state sampler qualification
status: proposed design; not yet publicly preregistered or executed
last_updated: 2026-09-13
paper_source: false
---

# MM-3 design after sampler qualification

SparseMix-2 supports DE + snooker sampling at both locked sparse states.
[Source E14](../evidence/Evidence-Sources.md#e14) supplies the full diagnostic
decision. MM-3 is proposed as a separate model-mismatch campaign; no MM-3
scientific endpoint has been computed and the executable campaign
registration has not yet been released.

## Intended comparison

The successor retains the four generating scenarios, eight acquisition
policies, common candidate-indexed outcomes, latent holdout, local precision
gate and endpoint definitions from the
[MM-2 protocol](Model-Mismatch-V2-Preregistration.md). New seeds are
10100--10129, outside the development, MM-1 and MM-2 sets. This gives a planned
120 scenario--seed tasks. These are prospective design quantities, not results.

The scientific change is numerical inference. The prior and one-pole
inference model remain unchanged; the sampler does not acquire access to the
generating parameters or discrepancy terms. MM-1 and MM-2 remain non-admitted
and their endpoint records are not pooled with MM-3.

## Production inference contract

The proposed implementation uses the same `emcee` 3.1.6 DE/snooker moves and
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

## Before execution

The production sampler integration check and full test suite must pass on
compute nodes. The final executable configuration, immutable source revision
and this protocol must then be publicly committed before any MM-3 outcome is
generated. Gate-aligned utility and simulation-based calibration remain
deferred until a new mismatch campaign has an admitted result.
