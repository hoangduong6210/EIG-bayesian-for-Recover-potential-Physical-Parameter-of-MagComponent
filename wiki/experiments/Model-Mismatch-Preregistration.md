---
title: Model-Mismatch Campaign MM-1
status: preregistered; no confirmatory result admitted
last_updated: 2026-08-26
paper_source: false
---

# Model-mismatch campaign MM-1

MM-1 asks whether the acquisition conclusions survive when synthetic data do
not come from the model used for inference. It is a new experiment, separate
from the completed matched-model benchmark. Its configuration is fixed in
`configs/model_mismatch.toml`. No MM-1
number belongs in the manuscript until all declared seed--scenario records
pass validation and a release containing those records is frozen.

## Scientific question

The existing benchmark draws data from the same Steinmetz and one-pole
Cole--Cole equations used by the posterior. MM-1 retains that inference model
but changes the data generator. The study measures three distinct outcomes:

1. whether each policy reaches the original two-target precision gate;
2. whether a narrow posterior is accurate at the two gate targets; and
3. whether latent predictions remain accurate and calibrated on a disjoint
   frequency, flux-density, and temperature grid.

The campaign is not a test of laboratory time, real-material transfer, or the
universal optimality of any acquisition policy.

## Fixed data-generating scenarios

All scenarios share the same six-parameter prior-predictive anchor within a
seed. The inference prior remains `DatasheetPrior()` and is not reconstructed
from the realized truth.

The permeability generator partitions \(\mu_s-1\) between two relaxation
terms,

\[
\mu^*(f)-1 = \sum_{j=1}^{2}
\frac{w_j(\mu_s-1)}{1+(i f/f_j)^{1-\alpha_j}},
\qquad w_1+w_2=1.
\]

The core-loss generator multiplies the Steinmetz response by

\[
\exp\!\left[
\gamma_T(T-25)
+q_f\log_{10}^2(f/10^5)
+q_{fB}\log_{10}(f/10^5)\log_{10}(B/0.1)
\right].
\]

The exact coefficients are in the configuration rather than prose alone. The
four fixed scenarios are:

- a matched control with one permeability pole and zero discrepancy terms;
- a two-pole permeability case with unchanged core loss;
- a temperature-dependent, non-separable core-loss case with one permeability
  pole; and
- a combined case with the larger declared permeability and core-loss
  deviations.

These cases are controlled stress tests. They are not estimates of the true
discrepancy of a named ferrite material.

## Candidate outcomes and seeds

The acquisition library retains the 37 exact 25-degree-Celsius designs from
benchmark v4. Temperatures outside 25 degrees Celsius are holdout-only because
the inference model treats temperature replicas as information-identical;
putting such replicas in the acquisition set would make policy comparisons
depend on arbitrary tie breaking. The 39-point holdout is disjoint from every
acquisition candidate and contains 24 core-loss points across 25, 60, and 100
degrees Celsius.

MM-1 uses seeds 8100--8129. Seeds 7300--7329 from the completed comparator
benchmark are explicitly forbidden for utility tuning or confirmatory reuse.
For a given seed and design, every policy receives the same stored outcome.
The standardized Gaussian draw is also shared across scenarios, allowing a
scenario contrast without adding a second noise realization.

The task matrix is therefore 4 scenarios by 30 seeds, or 120 independent
scenario--seed jobs. Each job runs the same eight policies used in benchmark
v4. EIG uses the previously qualified nested-Monte-Carlo setting supplied by
a locked estimator-decision file from release
`20260817T072230Z_401e3030fe13`. Its preregistered SHA-256 is
`eb334ae2c188f12e7f544be71b6f0c40be15913ceec0df60e5bf9a9258ed82b6`;
the runner rejects any other file. MM-1 does not select a new setting from its
own outcomes.

## Endpoints fixed before execution

The precision gate remains the central 90% latent-mean interval half-width at
\(P_v(100\,\mathrm{kHz},0.1\,\mathrm T,25^\circ\mathrm C)\leq8\%\) and
\(L_m(100\,\mathrm{kHz},25^\circ\mathrm C)\leq5\%\). For every policy and
scenario, aggregation reports:

- failure-to-reach-gate count and rate;
- measurement count and modeled cost among seeds that reach the gate;
- per-channel holdout relative RMSE and latent 90% interval coverage;
- core-loss holdout error and coverage by temperature; and
- false-confidence count and rate.

False confidence is declared when the precision gate is reached but the
posterior median has more than 8% absolute relative error at the core-loss
target or more than 5% at the inductance target. This definition distinguishes
posterior precision from accuracy without changing the stopping policy.

Strong-comparator contrasts retain their existing pairings: raw EIG against
raw predictive variance and raw Laplace D-optimality for measurement count,
and cost-normalized EIG against the corresponding cost-normalized policies for
modeled cost. Differences are comparator minus EIG, so a positive value favors
EIG. Each contrast reports its paired differences, mean, median, sample
standard deviation, and deterministic 95% percentile-bootstrap interval for
the mean using 10,000 paired-seed resamples. The bootstrap stream is derived
from the fixed scenario, policy, comparator, and endpoint names. A paired count
or cost difference is computed only when both policies reach the gate. Excluded
pairs and both policies' failure counts are reported, so conditioning cannot
hide a failure.

## Admission rule

An MM-1 result may enter the research record only after all 120 declared
records exist, every posterior state passes the existing convergence gate, the
aggregate reconstructs from those records, and the campaign is frozen under a
new release identity. Partial arrays, failed sampler states, and pilot runs are
diagnostics only. The matched-model release remains unchanged regardless of
the MM-1 outcome.

## Execution and monitoring

MM-1 is submitted only from an immutable run prepared from a clean commit on a
filesystem shared by login and compute nodes:

```bash
bash scripts/submit.sh --prepare-only
bash scripts/submit_model_mismatch.sh \
  runs/<prepared-run> <qualified-estimator-decision.json>
bash scripts/watch_model_mismatch.sh runs/<prepared-run>
```

The submission wrapper accepts only numeric scheduler job IDs and records the
array milestone before requesting the dependent aggregate. A scheduler error
or malformed response creates a failure record rather than a success marker.
The watcher is read-only and exits only after the aggregate exists or a task,
submission, or aggregation failure is recorded.

The campaign deliberately does not introduce a gate-aligned utility or
simulation-based calibration. Those are later experiments and must use their
own prospective configurations and seed namespaces.
