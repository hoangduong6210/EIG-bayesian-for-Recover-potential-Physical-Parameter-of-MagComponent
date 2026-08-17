# Bayesian calibration and sequential design for magnetic-core models

This repository studies sequential measurement selection for joint Bayesian
calibration of Steinmetz core-loss and Cole--Cole complex-permeability models.
The implementation covers posterior inference, expected information gain
(EIG), paired acquisition-policy benchmarks, estimator qualification, measured-
data model checks, and frozen evidence.

The scope is the magnetic-component case study. Results from unrelated device
domains are not included.

## Main result

The 30-paired-seed matched-model benchmark does not show an EIG advantage over
the two strong acquisition comparators.

| Comparison | Result | Interpretation | Source |
|---|---|---|---|
| Raw EIG vs predictive variance | Both reach the gate in 5 measurements for all 30 pairs | Tie on measurement count | [E4](wiki/Evidence-Sources.md#e4) |
| Raw EIG vs Laplace D-optimality | Both reach the gate in 5 measurements for all 30 pairs | Tie on measurement count | [E4](wiki/Evidence-Sources.md#e4) |
| EIG/cost vs predictive variance/cost | Predictive variance uses 15.17 fewer modeled-cost units on average and wins all 30 pairs | EIG/cost loses on the declared cost-to-gate endpoint | [E4](wiki/Evidence-Sources.md#e4) |
| EIG/cost vs Laplace D-optimality/cost | Equal modeled cost in all 30 pairs | Tie on modeled cost | [E4](wiki/Evidence-Sources.md#e4) |
| Raw EIG vs fixed channel-balanced traversal | 5 versus 9 measurements | Improvement over this specified traversal only | [E4](wiki/Evidence-Sources.md#e4) |

The trajectory audit explains the negative result. Raw policies follow
different rankings but finish the complementary core-loss and permeability
measurements at the same discrete gate step. EIG/cost spends an additional
low-cost measurement on an already-satisfied inductance target before taking
the core-loss point needed to stop. [Trajectory evidence](wiki/Evidence-Sources.md#e5)

## Start here

| Need | Document |
|---|---|
| Research overview and navigation | [Wiki index](wiki/Wiki-Index.md) |
| Full methods and scientific argument | [Full manuscript](wiki/Full-Manuscript.md) |
| Completed computations and comparator analysis | [Scientific job results](wiki/Scientific-Job-Results.md) |
| Supported and unsupported claims | [Claims and limits](wiki/Claims-and-Limits.md) |
| Numerical source map | [Evidence sources](wiki/Evidence-Sources.md) |
| Reproduction and audit chain | [Reproduce and audit](wiki/Reproduce-and-Audit.md) |
| Historical and rendered paper versions | [Paper directory](paper/README.md) |

## Evidence scope

Supported conclusions are limited to:

- matched-model synthetic recovery as an implementation check;
- paired policy outcomes under the finite candidate library and local
  two-target precision gate;
- modeled acquisition cost using the prespecified cost table;
- in-sample adequacy of accepted measured-data fits.

The evidence does not establish laboratory-time savings, global six-parameter
identification, calibrated physical uncertainty, robustness under structural
model mismatch, or a validated optimal laboratory plan. Accepted permeability
fits retain large loss-component residuals, with \(\mu''\) RRMSE of
36.77%--52.42%, so measured-data acquisition suggestions remain conditional on
an inadequate one-pole model. [Measured-data evidence](wiki/Evidence-Sources.md#e7)

## Evidence release

The wiki results are bound to release
`20260817T072230Z_401e3030fe13`, release-manifest SHA-256
`85448a2c3c9db2db051c94543d8a336e7157d55289f10c1792e9c57d433812f7`.
The disclosure-safe numerical projection is
[`wiki/evidence/results.json`](wiki/evidence/results.json); its source map and
integrity contract are documented in
[`wiki/Evidence-Sources.md`](wiki/Evidence-Sources.md). [Release evidence](wiki/Evidence-Sources.md#e8)
The raw-to-aggregate verification steps are listed in
[`wiki/Reproduce-and-Audit.md`](wiki/Reproduce-and-Audit.md).

## Models and measured-data scope

| Response | Forward model | Active parameters | Measured-data records used in aggregate results |
|---|---|---|---|
| Core-loss density | Isothermal Steinmetz law | `k`, `alpha`, `beta` | N49, N87, N95, and 3C95 temperature cohorts |
| Complex permeability | One-pole Cole--Cole law | `mu_s`, `f_rel`, `alpha_cc` | Accepted N87 and N95 LEA-MTB records |

Raw measured curves are not redistributed. Upstream file identities and
checksums are declared in [`data/manifest.yaml`](data/manifest.yaml) and
[`data/checksums.sha256`](data/checksums.sha256).

## Test the repository

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
pytest
python wiki/build.py check
```

The validation suite checks implementation contracts, evidence bindings,
public-disclosure rules, manuscript citations, wiki navigation, and snapshot
build capability. Full MCMC and EIG campaigns require the pinned environment
and compute workflow described in [`docs/COMPUTE_POLICY.md`](docs/COMPUTE_POLICY.md).

## Repository map

| Path | Contents |
|---|---|
| [`wiki/`](wiki/) | Research narrative, result ledger, evidence map, and paper source |
| [`src/magcore_calib/`](src/magcore_calib/) | Forward models, priors, inference, EIG, and diagnostics |
| [`experiments/`](experiments/) | Scientific experiment entry points |
| [`configs/`](configs/) | Model, sampler, acquisition, dependency, and seed settings |
| [`results/`](results/) | Published evidence projections and frozen releases |
| [`tests/`](tests/) | Unit, schema, evidence, and release-contract tests |
| [`docs/`](docs/) | Protocol, provenance, claim boundaries, and compute policy |
| [`paper/`](paper/) | Conference record and rendered full-paper snapshot |

Citation metadata are provided in [`CITATION.cff`](CITATION.cff). Software is
released under the MIT License; upstream data retain their original licenses
and attribution requirements.
