---
title: Model-Mismatch Campaign MM-2
status: preregistered before confirmatory outcomes
last_updated: 2026-08-28
paper_source: false
---

# Model-mismatch campaign MM-2

MM-2 is the independent confirmatory successor to the non-admitted MM-1
campaign. It retains the scientific question, data-generating scenarios,
policies, acquisition library, holdout, endpoints, estimator setting, and
convergence thresholds. It changes the confirmatory seed namespace and the
maximum adaptive-sampling allowance. The machine-readable contract is
[`configs/model_mismatch_v2.toml`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/configs/model_mismatch_v2.toml).

No MM-2 task had been run when this protocol and configuration were committed.
The predecessor binding is the endpoint-blind MM-1 non-admission record with
SHA-256
`dba31b989debfe1729261a0fb42e07317069a97095b743c0d73237500e5a5207`.
[Source E10](../evidence/Evidence-Sources.md#e10)

## Fixed and changed contracts

| Contract component | MM-2 rule |
|---|---|
| Data generators | The four MM-1 scenarios, unchanged |
| Policies | The same eight-policy registry |
| Candidate and holdout libraries | Unchanged |
| Precision and false-confidence thresholds | Unchanged |
| Nested-EIG setting | Same locked decision file and SHA-256 |
| Confirmatory seeds | New namespace `mm2_confirmatory_seed_v1`, seeds 9100--9129 |
| Forbidden observed seeds | Benchmark-v4 seeds 7300--7329 and MM-1 seeds 8100--8129 |
| Minimum retained MCMC steps | 20,000 |
| Check interval | 10,000 retained steps |
| Maximum retained MCMC steps | 320,000 |
| Convergence thresholds | Unchanged: ESS, steps per autocorrelation time, acceptance, and finite log probability |

The larger maximum is a computational allowance, not a relaxed diagnostic.
Every posterior state is checked at the same intervals and stops at the first
valid checkpoint. A state that remains invalid at 320,000 retained steps
causes its entire scenario--seed task to fail admission.

## New rejection record

If a task reaches the sampler cap without passing validation, no claim-bearing
`result.json` is created. Instead, an immutable rejection sidecar records:

- campaign, scenario, seed, configuration, and posterior-state identities;
- the affected policy names and deterministic MCMC seeds;
- autocorrelation time, effective sample size, steps per autocorrelation time,
  acceptance fraction, retained-step count, and stopping reason; and
- an explicit declaration that the sidecar contains no scientific endpoint
  value and is not a claim-bearing result.

Rejection sidecars are stored outside the aggregate input tree. The aggregate
still requires the exact 120-result matrix and cannot treat a rejection as a
valid result.

## Pairing and endpoints

Each seed again defines one prior-predictive truth anchor shared by all four
scenarios. Candidate-indexed standardized noise is shared across policies and
scenarios within that seed. The disjoint holdout is never used for acquisition
or stopping.

The endpoints remain those declared for MM-1: gate reach and failure,
measurement count, modeled cost, latent holdout error and 90% interval
coverage, temperature-stratified core-loss performance, false confidence, and
the four paired strong-comparator contrasts. Definitions and denominators are
unchanged from the [MM-1 protocol](Model-Mismatch-Preregistration.md).

## Admission rule

MM-2 enters the research record only if all 120 scenario--seed tasks produce
valid results, every posterior state passes the unchanged convergence gate,
the aggregate reconstructs from the exact matrix, and the resulting campaign
is frozen under a new evidence-release identity. Any failed task closes MM-2
as non-admitted; no seed replacement, partial aggregate, or mixed-protocol
salvage is allowed.

## Execution

The run is prepared from a clean commit on compute-node shared storage. Both
the source archive digest and extracted source tree are checked before
submission and again on the compute node.

```bash
bash scripts/submit.sh --prepare-only
bash scripts/submit_model_mismatch_v2.sh \
  runs/<prepared-run> \
  <qualified-estimator-decision.json> \
  <MM-1-non-admission.json>
bash scripts/watch_model_mismatch_v2.sh runs/<prepared-run>
```

Gate-aligned utility and simulation-based calibration remain separate future
protocols and cannot alter MM-2 while it is running.
