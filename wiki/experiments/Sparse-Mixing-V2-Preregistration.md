---
title: SparseMix-2 prospective sampler validation
status: registered and submitted; validation pending
last_updated: 2026-09-12
paper_source: false
---

# SparseMix-2: prospective sampler validation

## Scientific question and registration boundary

Does differential evolution mixed with snooker proposals give reproducible
posterior exploration at both locked sparse states under a fixed long-run
protocol? The exploratory pilot motivates the method but does not answer this
confirmatory question. [Pilot evidence E13](../evidence/Evidence-Sources.md#e13)

This registration follows inspection of the complete pilot and precedes every
SparseMix-2 chain. The executable contract is
[`configs/sparse_mixing_v2.toml`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/configs/sparse_mixing_v2.toml).
Its committed revision, configuration hash, bound pilot-decision hash and
source archive identify the registration. No criterion may be changed within
this study after sampling begins.

## Fixed state and sampling design

The submitted run is `20260912T060428Z_7a00dff3106f`, from registration commit
`7a00dff3106fa72027f243b94b7b512391b2548c`. Configuration SHA-256:
`89ac040be89cc248088c5ed42288645717e792b9cf2113cf413298db8a41092c`.
The [registration record](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/results/diagnostics/sparse_mixing/SparseMix-2/20260912T060428Z_7a00dff3106f/registration.json)
records submission, not completion or diagnostic passage. Independent
full-chain validation follows successful completion of the entire array.

The two targets are the exact n3 and n4 observation states reconstructed from
the MM-2 rejection, with the same state and observation hashes as SparseMix-1.
Their posterior density, prior, observations and six active coordinates are
unchanged. Neither generating-parameter proximity nor an acquisition endpoint
is consulted. [State record E12](../evidence/Evidence-Sources.md#e12)

Each state has two initialization families, local prior-center and
overdispersed prior Latin-hypercube, with four independent ensembles per family:
16 tasks in total. Each ensemble has 48 walkers, 80,000 discarded warmup steps
and 800,000 retained steps. No early stopping is allowed. Diagnostics are
recorded at 20,000, 40,000, 80,000, 160,000, 320,000, 480,000, 640,000 and
800,000 retained steps. These are protocol quantities, not observed outcomes.

The initialization seed is derived from `SparseMix-2`, state identity,
initialization family and replicate. The sampler uses the separate
`SparseMix-2/de_snooker` namespace. These seeds are distinct from the pilot and
SparseMix-1 namespaces. No pilot chain is extended or reused.

The implementation is `emcee` 3.1.6. `DEMove` has mixture weight 0.8,
`sigma=1e-5`, `gamma0=2.38/sqrt(12)`, two splits and randomized splitting.
`DESnookerMove` has weight 0.2, `gammas=1.7`, four splits and randomized
splitting. Sampling and diagnostics use the original active coordinates;
the selected method introduces no additional transformation. The vectorized
density must agree with the locked scalar implementation at initialization
and at the last walker positions.

## Prospective passage rule

Every ensemble must satisfy every within-chain criterion for every active
parameter. Every independent-ensemble pair must satisfy both quantile
criteria. Missing or undefined values fail the rule.

| Check | Required condition |
|---|---|
| Finite retained log density | Fraction equals 1 |
| Steps per estimated autocorrelation time | At least 50 for each parameter |
| Effective sample size | At least 400 for each parameter |
| Relative change in τ | At most 0.10 between 640,000 and 800,000 steps, divided by the latter estimate |
| Retained mean acceptance | Within [0.05, 0.80] |
| Pairwise median difference | At most max(2 pooled MCSE, 0.10 pooled SD) |
| Pairwise 5th/95th-percentile difference | At most 0.15 pooled IQR |

Pooled SD is the root mean square of the two ensemble SDs. Pooled MCSE is
the square root of the sum of the two squared SDs divided by their respective
ESS values. Pooled IQR is the arithmetic mean of the two IQRs. ESS here uses
the ensemble autocorrelation estimator; these tests are not a proof of
convergence or simulation-based calibration.

Acceptance is a broad proposal-specific sanity check. The original
diagnostic report's narrower acceptance flag is retained in the record but
does not control this new rule. All other mixing and between-ensemble checks
remain mandatory. This distinction is frozen before the confirmatory chains.

## Evidence retention and failure handling

Each task saves the full, unthinned original-coordinate chain, retained log
probabilities, initial walker positions, every checkpoint diagnostic, final
quantiles and SHA-256-bound completion markers. Independent validation
recomputes autocorrelation, ESS and quantiles from the saved arrays. Acceptance
cannot be recomputed without proposal histories; its range and consistency
are checked separately.

The matrix must contain all 16 tasks and 48 artifacts. A missing task or corrupt
artifact prevents a complete decision. Infrastructure retries, if needed, use
the same seed and configuration in a separately identified attempt and never
overwrite a result. Diagnostic failure is not an infrastructure retry and
must not trigger extension, reseeding or a relaxed threshold within SparseMix-2.

## Conditional continuation

The study supports mixing at the two tested states only when all eight
ensembles pass at n3 **and** all eight pass at n4. Only that result permits
registration of a new, independent model-mismatch campaign. The new campaign
still requires its own state-level checks: two qualifying states do not
guarantee convergence throughout an acquisition trajectory.

If either state fails, the mismatch campaign remains closed and this study is
reported as non-passing. MM-1 and MM-2 remain permanently non-admitted under
either outcome. Gate-aligned utility and simulation-based calibration are
deferred until the new mismatch study has an admitted result. No laboratory
time-saving, recovery, coverage or acquisition-policy claim follows from
SparseMix-2 itself.
