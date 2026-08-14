# Experiment protocol

This document specifies the Magnetic-only experiment comparison. Configuration
files are authoritative for exact sample counts and budgets; a frozen release
records their hashes.

## E1 — Identifiability

Compute the Fisher spectrum over the exact active inference vector. If the Cole--Cole broadening parameter is inferred, it must be included. Report scaling, eigenvalues, eigenvectors, condition number, finite-difference/automatic-differentiation method, and design library. Do not reuse a spectrum produced for a different parameter dimension.

## E2 — Matched-model synthetic recovery

- Seeds: 42, 43, 44, 45, 46.
- Generate observations from the declared Steinmetz and Cole--Cole forward models.
- Report truth, posterior median, 90% interval, relative recovery error, sampler diagnostics, and posterior-predictive precision.
- Call this a matched-model synthetic test; it is not external validation.

## E3 — EIG efficiency

This campaign separates estimator selection from confirmatory evaluation:

- Estimator-validation state seeds: 7100--7103, each at 2, 4, and 6 fixed-traversal
  observations.
- Downstream-validation seeds: 7200--7209.
- Confirmatory acquisition seeds: 7300--7329 (30 paired seeds).
- Recovery seeds remain 42--46 and are not acquisition replicates.

The sets are disjoint. Estimator validation must write and hash its final
decision before the confirmatory acquisition array can start. Confirmatory
seeds may not be used to tune the estimator.

The prespecified estimator-validation grid is
$n_{\rm outer}\in\{100,300,900\}$,
$n_{\rm inner}\in\{50,100,300\}$, and replicate prefixes
$R\in\{5,10,20\}$. The reference is $(1200,400,40)$ and the doubled-budget
audit is $(2400,800,40)$ at the first state seed with 2 and 6 observations.
Estimator comparisons use prefix-nested random streams and a fixed
state/design noise scale, so budgets estimate the same mathematical target.
Top-1 stability is the deterministic paired bootstrap probability that the
implemented replicate-mean selectors agree, not agreement between noisy
single-replicate winners. The candidate and reference mean winners must each
also recur in at least 80% of bootstrap resamples. All candidate rows are
sorted by stable design key before deterministic tie breaking. Comparisons
fail closed unless their saved RNG seeds match and both declare prefix nesting.
If no cheaper grid cell passes, the verified reference is the prespecified
conservative fallback; if the higher-budget comparison fails, the campaign
does not produce an acquisition result.

The selector acts on replicate-mean scores. Stability is therefore evaluated
for the replicate-mean winner rather than for individual-replicate winners.

Compare raw-EIG and EIG-per-modeled-cost acquisition with a deterministic fixed
channel-balanced grid traversal using the same two initial observations,
candidate library, pre-generated candidate-indexed outcomes, maximum budget,
and stopping rule. The comparator must not be called uniform random or
space-filling. The isothermal candidate library must contain no
temperature-only duplicates of the implemented forward laws.

Use stable candidate identity rather than list position to seed every EIG score.
Repeat each nested-Monte-Carlo estimate and retain its standard deviation,
standard error, 95% Monte Carlo interval, and top-rank frequency. Report raw
EIG against measurement count, EIG/cost against total modeled acquisition cost,
and, for each endpoint, per-seed outcomes, failures, paired differences,
mean/median, sample standard deviation, bootstrap interval, and paired win rate.
Do not report only a ratio of aggregate means.

The gate is the central 90% interval half-width of the noise-free latent mean
response divided by its posterior median at exactly two targets:
$P_v(100\,\mathrm{kHz},0.1\,\mathrm T,25\,^{\circ}\mathrm C)\leq8\%$ and
$L_m(100\,\mathrm{kHz},25\,^{\circ}\mathrm C)\leq5\%$. It is a local precision
rule, not evidence of truth proximity, parameter recovery, global prediction,
model adequacy, or frequentist coverage.

### E3-v4 — preregistered comparator extension (not in the current frozen result)

The next confirmatory release uses the same 30 acquisition seeds and adds five
declared policy variants to the three-policy comparison: a seeded random
channel-balanced traversal, raw and cost-normalized greedy predictive variance,
and raw and cost-normalized local Laplace D-optimality. Every policy uses the
same truth, exact-identity outcome table, initial observations, candidate set,
gate, count budget, and modeled-cost table. Randomization has a policy-specific
SHA-256 seed namespace independent of the outcome stream. Greedy score records
must retain every candidate score and exact design identity at every decision.

Primary comparisons remain paired against the fixed channel-balanced reference:
count-targeting policies use measurements-to-gate and cost-targeting policies
use modeled cost-to-gate. Random and fixed traversals are descriptive controls.
The benchmark supports pairwise conclusions for these declared policies; it
does not establish global optimality over all acquisition methods.

At the final state of every policy, the pipeline also records six-parameter
truth recovery and per-channel latent-mean error and 90% interval coverage on a
prespecified 23-point grid disjoint from all acquisition candidates. These are
secondary diagnostics and are prohibited from acquisition and stopping. They
test for a narrow-but-wrong posterior within the matched-model simulation; they
do not remove structural-model dependence or establish real-material accuracy.

This section preregisters code and endpoints only. Until a new checksum-locked
release contains all 30 valid v4 records, the repository makes no numerical
claim for any added comparator or secondary validation endpoint.

## E4 — Prior-center offset sensitivity

Run declared dimensionless prior-center offset levels 0.00, 0.15, and 0.30.
These are labels for the explicitly coded coordinate shifts, not uniform
percentage perturbations of every physical parameter. Record exactly which
physical/transformed parameters are shifted. Report recovery and predictive
performance separately; a precision gate reached around a biased posterior
does not establish accuracy. This study is prior sensitivity, not structural
forward-model misspecification.

## E5 — Public measured complex permeability

Declared material/source pairs:

- N95 / LEA-MTB
- N87 / LEA-MTB
- N87 / MagNet
- 3C95 / MagNet

Report the storage and loss components separately. Show frequency coverage relative to inferred relaxation frequency and disclose active bounds. Do not attribute poor loss-component fit solely to coverage unless a model-comparison or posterior-predictive diagnostic supports that inference.

## E6 — Public core-loss curves

Declared materials: N49, N87, N95, and 3C95. Validate units and physical ranges before fitting. Record every exclusion rule before seeing fit quality, including the physical flux-density guard. Report RMS error, residual structure, fitted exponents, uncertainty, and the temperature subset. The present Steinmetz implementation is temperature-independent; notation and claims must reflect that limitation.

## E7 — Synthetic lot sensitivity

If retained, label this experiment “synthetic lot sensitivity.” Report injected effects, recovery intervals, seeds, and pairwise separation rule. It is not evidence that physical manufacturing lots were separated.

## Evidence acceptance criteria

- All expected tasks and seeds are present.
- Sampler diagnostics meet declared thresholds or failures are disclosed.
- Result schemas and provenance validate.
- Figures/tables reproduce from a single frozen release.
- Every quantitative manuscript claim maps to a frozen artifact.
- Limitations include matched-model dependence, public-data scope, model discrepancy, and model-conditional uncertainty.
