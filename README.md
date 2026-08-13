# Expected-information-gain-guided Bayesian calibration of magnetic-core models

This repository accompanies a six-page conference study of Bayesian calibration
and sequential measurement selection for Steinmetz core-loss and Cole--Cole
complex-permeability models. It contains the manuscript, implementation,
prespecified protocol, and checksum-locked evidence for the **magnetic-component
case study only**.

[Read the current paper (PDF)](paper/current_state/manuscript.pdf) ·
[Browse manuscript versions](paper/README.md) ·
[Audit the conference snapshot](paper/conference_snapshot/README.md) ·
[Inspect the claim register](docs/CLAIMS_EVIDENCE.md) ·
[Read the experiment protocol](docs/EXPERIMENT_PROTOCOL.md) ·
[Verify the frozen evidence](results/frozen/20260812T035654Z_a0703698ace9)

## Scientific summary

**Question.** Can expected information gain (EIG) reduce the number or modeled
cost of measurements needed to narrow posterior-predictive uncertainty for a
specified magnetic-core calibration task?

**Approach.** Six Steinmetz and Cole--Cole parameters are inferred jointly in a
matched-model synthetic experiment. Raw EIG and EIG divided by a prespecified
measurement cost are compared separately with a deterministic fixed
channel-balanced traversal. Every policy sees the same synthetic truth, initial
observations, candidate library, candidate-indexed noisy outcomes, maximum
budget, and stopping rule.

**Answer within the tested setting.** Across 30 prespecified paired seeds, raw
EIG reached the local two-target precision gate in 4--5 measurements, versus 9
for the fixed traversal. The mean paired count reduction was 44.8%. EIG per
modeled cost reduced the corresponding prespecified cost by 34.4%. Both results
are conditional on the matched forward model and the local stopping rule; they
are not claims of globally accurate component identification or laboratory-time
savings.

## Evidence at a glance

| Scientific question | Design and endpoint | Frozen result | Interpretation |
|---|---|---|---|
| Are all six active coordinates locally observable? | Scaled local Fisher matrix | Rank 6; condition number `2.35 × 10^4` | Full local rank with strong sensitivity anisotropy; not global identifiability |
| Does inference recover known parameters when the model is correct? | Five prior-predictive matched-model seeds | Per-parameter median errors `0.27%--5.85%`; truth in `28/30` equal-tailed 90% intervals | Implementation-level recovery check; five seeds do not establish frequentist coverage |
| Does raw EIG reduce measurement count? | 30 paired seeds; common two-target precision gate | `4--5` versus `9` measurements; mean paired reduction `44.8%`; mean paired difference `4.03` measurements (bootstrap 95% CI `4.00--4.10`); `100%` wins; `0` failures | Supported for this matched-model count endpoint |
| Does EIG/cost reduce modeled acquisition cost? | 30 paired seeds; prespecified cost units | Mean paired reduction `34.4%` (bootstrap 95% CI `34.31%--34.48%`); `100%` wins; `0` failures | Supported for modeled cost, not measured laboratory time |
| How adequate are the low-order models on measured records? | In-sample relative RMS error on accepted public-data fits | Core loss `8.79%--18.21%`; permeability `mu'` `6.89%--9.33%`; `mu''` `36.77%--52.42%` | The large `mu''` residuals expose discrepancy in the one-pole permeability model |

All values above are generated from immutable release
`20260812T035654Z_a0703698ace9`. Their machine-readable source is
[`paper_summary.json`](results/frozen/20260812T035654Z_a0703698ace9/tables/paper_summary.json),
and their permitted interpretation is defined in the
[`claims-to-evidence register`](docs/CLAIMS_EVIDENCE.md).

## What was compared

```text
Declared prior ── draw hidden truth ── pre-generate one outcome per candidate
                                              │
                 ┌────────────────────────────┼───────────────────────────┐
                 │                            │                           │
              raw EIG                  EIG / modeled cost       fixed channel-balanced
          minimize count-to-gate       minimize cost-to-gate          traversal
                 │                            │                           │
                 └──────────── paired evaluation under one gate ─────────┘
```

The gate is the central 90% interval half-width of the **noise-free latent mean
response**, divided by its posterior median, at exactly two targets:

- core loss at `100 kHz`, `0.1 T`, `25 °C`: at most `8%`;
- magnetizing inductance at `100 kHz`, `25 °C`: at most `5%`.

This gate measures local posterior precision. It does not test truth proximity,
six-parameter recovery, prediction over the full frequency/flux domain,
uncertainty calibration, or robustness to model misspecification.

## Benchmark design

The comparison uses the following controls:

1. **No truth-centered prior or initialization.** Synthetic truth is drawn from
   the declared prior predictive distribution; the prior and MCMC initialization
   remain centered on the independently declared datasheet prior.
2. **Paired observations.** One noisy outcome is generated for each stable
   candidate identity and shared by every policy, separating policy effects from
   noise-realization effects.
3. **No temperature-only duplicates.** The candidate library is isothermal
   because the implemented forward laws are temperature independent.
4. **Precisely named comparator.** The baseline is a deterministic fixed
   channel-balanced traversal, not uniform random sampling or a space-filling
   design.
5. **Aligned objectives.** Raw EIG is evaluated by measurement count; EIG/cost
   is evaluated separately by total modeled cost.
6. **Order-invariant stochastic scoring.** EIG random streams are derived from
   a SHA-256 key of the physical design tuple rather than list position.
7. **Estimator uncertainty and convergence.** Scores retain repeated-estimator
   SD, SE, 95% Monte Carlo intervals, and top-rank frequencies. Estimator
   validation evaluated 27 budgets over 12 fixed posterior states, then selected
   the verified `(1200 outer, 400 inner, 40 replicates)` reference before the
   30-seed confirmatory comparison. A doubled-budget comparison and ten downstream
   seeds preserved both policy endpoints.

The full controls and prespecified thresholds are in
[`docs/EXPERIMENT_PROTOCOL.md`](docs/EXPERIMENT_PROTOCOL.md).

## Scope of the evidence

### Supported

- Matched-model six-parameter recovery as a five-seed implementation check.
- Fewer measurements for raw EIG than the fixed traversal under the declared
  paired synthetic benchmark and local precision gate.
- Lower prespecified modeled acquisition cost for EIG/cost under the same
  benchmark.
- In-sample model-adequacy metrics for the retained public measured records.

### Not established

- Calibrated uncertainty, held-out accuracy, or global parameter
  identifiability.
- Robustness to shifted priors or forward-model misspecification.
- Temperature-dependent prediction from the temperature-independent Steinmetz
  implementation.
- Stable measured-data EIG rankings or a validated optimal laboratory plan.
- Measured laboratory-time, schedule, qualification, or physical-testing
  savings.

Measured-data EIG rankings are withheld because the repeated-estimator audit did
not support a stable ranking. N87 and 3C95 MagNet permeability fits are retained
only as excluded diagnostics. These limitations are part of the result, not
post-hoc qualifications.

## Models and data

| Response | Forward model | Active parameters | Measured-data scope |
|---|---|---|---|
| Core-loss density | Isothermal Steinmetz law | `k`, `alpha`, `beta` | N49, N87, N95, and 3C95 temperature cohorts |
| Complex permeability | One-pole Cole--Cole law | `mu_s`, `f_rel`, `alpha_cc` | Convergence-valid N87 and N95 LEA-MTB records |

Raw measured data are not redistributed. The selected upstream files and their
SHA-256 digests are declared in [`data/manifest.yaml`](data/manifest.yaml) and
[`data/checksums.sha256`](data/checksums.sha256). See
[`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md) for acquisition and staging
instructions.

## Reproduce and verify

### 1. Run the validation suite

Python 3.11 or newer is required because the experiment-plan loader uses the
standard-library `tomllib` module.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
pytest
```

These tests validate implementation, schemas, and release contracts without
launching MCMC, EIG sweeps, full fits, figure generation, or scheduler jobs.

### 2. Verify the published evidence byte-for-byte

```bash
cd results/frozen/20260812T035654Z_a0703698ace9
sha256sum --check checksums.sha256
```

The manuscript is locked to this release by
[`paper/current_state/results.lock.yaml`](paper/current_state/results.lock.yaml).
Tables and figures are
generated artifacts rather than manually transcribed results.

### 3. Re-run the full campaign

Create the pinned environment from [`configs/dependencies.lock`](configs/dependencies.lock),
stage the manifest-listed measured inputs, adapt the scheduler headers, set
`MAGCORE_VENV` and optionally `MAGCORE_DATA_ROOT`, then run:

```bash
bash scripts/submit.sh
```

The heavy campaign is designed for SLURM compute nodes and stops without
publishing a release if the estimator decision is incomplete, required tasks
are missing, provenance is inconsistent, or frozen checksums change. See
[`docs/COMPUTE_POLICY.md`](docs/COMPUTE_POLICY.md) and
[`docs/RESULT_FREEZING.md`](docs/RESULT_FREEZING.md).

## Repository map

| Path | Contents |
|---|---|
| [`paper/`](paper/) | Current manuscript and conference snapshot in separate folders |
| [`results/frozen/20260812T035654Z_a0703698ace9/`](results/frozen/20260812T035654Z_a0703698ace9/) | Compact checksum-locked public evidence |
| [`src/magcore_calib/`](src/magcore_calib/) | Forward models, priors, inference, EIG, and diagnostics |
| [`experiments/`](experiments/) | Scientific experiment entry points |
| [`configs/`](configs/) | Model, sampler, acquisition, dependency, and seed settings |
| [`tests/`](tests/) | Unit, schema, and public-release contract tests |
| [`docs/`](docs/) | Protocol, provenance, claim boundaries, and compute policy |
| [`paper/current_state/source/`](paper/current_state/source/) | Reproducible LaTeX and Overleaf source |

## Citation and license

Citation metadata are provided in [`CITATION.cff`](CITATION.cff). The software
is released under the MIT License. Upstream measured data retain their original
licenses and attribution requirements.
