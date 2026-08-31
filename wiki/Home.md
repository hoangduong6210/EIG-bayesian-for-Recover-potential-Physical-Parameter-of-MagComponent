---
title: Bayesian Calibration and Sequential Design for Magnetic-Core Models
status: canonical current-research summary
last_updated: 2026-08-31
paper_source: false
---

# Bayesian calibration and sequential design for magnetic-core models

This repository studies sequential measurement selection for joint Bayesian
calibration of Steinmetz core-loss and Cole--Cole complex-permeability models.
It contains posterior inference, expected information gain (EIG), paired
acquisition-policy benchmarks, estimator qualification, measured-data model
checks, and frozen evidence for the magnetic-component case study.

Authors: Viet Hoang Duong, Viet Huy Duong, and Lun-Min Shih.

## Current result

The validated 30-paired-seed matched-model benchmark does not show an EIG
advantage over the two strong acquisition comparators.

| Comparison | Paired result | Defensible interpretation | Evidence |
|---|---|---|---|
| Raw EIG vs predictive variance | Both stop at 5 measurements in all 30 pairs | Tie on measurement count | [E4](evidence/Evidence-Sources.md#e4) |
| Raw EIG vs Laplace D-optimality | Both stop at 5 measurements in all 30 pairs | Tie on measurement count | [E4](evidence/Evidence-Sources.md#e4) |
| EIG/cost vs predictive variance/cost | Predictive variance uses 15.17 fewer modeled-cost units on average and wins all 30 pairs | EIG/cost loses on cost to gate | [E4](evidence/Evidence-Sources.md#e4) |
| EIG/cost vs Laplace D-optimality/cost | Equal modeled cost in all 30 pairs | Tie on modeled cost | [E4](evidence/Evidence-Sources.md#e4) |
| Raw EIG vs fixed channel-balanced traversal | 5 versus 9 measurements in all 30 pairs | Improvement over this specified traversal only | [E4](evidence/Evidence-Sources.md#e4) |

The recorded paths are consistent with objective--gate misalignment. The three
raw utilities rank the 37-candidate library similarly and finish the
complementary core-loss and permeability measurements at the same discrete
stopping step. Under cost normalization, EIG usually selects an inexpensive
inductance point before the core-loss point that controls the stopping gate;
predictive variance selects the gate-relevant core-loss point first. This is a
post hoc descriptive result for the present benchmark, not a general ordering
of acquisition methods. [Trajectory evidence E5](evidence/Evidence-Sources.md#e5)
and [selection-path evidence E9](evidence/Evidence-Sources.md#e9)

## Evidence boundary

The current evidence supports:

- matched-model synthetic recovery as an implementation check [E2](evidence/Evidence-Sources.md#e2);
- paired policy outcomes under the finite candidate library and local
  two-target precision gate [E4](evidence/Evidence-Sources.md#e4);
- modeled acquisition cost under the declared cost table [E4](evidence/Evidence-Sources.md#e4);
- in-sample adequacy diagnostics for accepted measured-data fits [E7](evidence/Evidence-Sources.md#e7).

It does not establish laboratory-time savings, global six-parameter
identification, calibrated physical uncertainty, robustness under structural
model mismatch, stable measured-data EIG rankings, or a validated optimal
laboratory plan. These boundaries are maintained in the
[claim registry](claims/Claims-and-Limits.md).

Accepted measured-data fits retain substantial loss-component discrepancy:

| Response | Accepted-fit RRMSE | Evidence |
|---|---:|---|
| Core-loss density | 8.79%--18.21% | [E7](evidence/Evidence-Sources.md#e7) |
| Storage permeability, \(\mu'\) | 6.89%--9.33% | [E7](evidence/Evidence-Sources.md#e7) |
| Loss permeability, \(\mu''\) | 36.77%--52.42% | [E7](evidence/Evidence-Sources.md#e7) |

The one-pole model does not reproduce the retained \(\mu''\) records adequately,
so measured-data acquisition suggestions remain model-conditional.
[E7](evidence/Evidence-Sources.md#e7)

## Research state

| Work product | State | Evidence or protocol |
|---|---|---|
| 30-seed, eight-policy matched-model benchmark | Validated | [E1](evidence/Evidence-Sources.md#e1), [E4](evidence/Evidence-Sources.md#e4) |
| Nested-EIG estimator setting | Qualified for the declared benchmark | [E3](evidence/Evidence-Sources.md#e3) |
| Public raw-to-aggregate audit bundle v2 | Published and independently verifiable | [E8](evidence/Evidence-Sources.md#e8) |
| Comparator selection-path analysis | Post hoc diagnostic complete | [E9](evidence/Evidence-Sources.md#e9) |
| Model-mismatch campaign MM-1 | Closed with 119/120 valid task records; not admitted | [E10](evidence/Evidence-Sources.md#e10), [MM-1 record](experiments/Model-Mismatch-Preregistration.md) |
| Model-mismatch campaign MM-2 | Closed with 119/120 valid task records and one prospectively retained sampler rejection; not admitted | [E11](evidence/Evidence-Sources.md#e11), [MM-2 record](experiments/Model-Mismatch-V2-Preregistration.md) |
| Sparse-posterior mixing diagnostic | Immutable 18-ensemble run active; no diagnostic classification yet | [SparseMix-1 protocol](experiments/Sparse-Posterior-Mixing-Preregistration.md) |
| Gate-aligned utility and simulation-based calibration | Deferred; neither non-admitted mismatch campaign can authorize these experiments | [Decision 0001](decisions/0001-gate-aligned-objective.md) |

The admitted evidence is bound to release
`20260817T072230Z_401e3030fe13`, manifest SHA-256
`85448a2c3c9db2db051c94543d8a336e7157d55289f10c1792e9c57d433812f7`.
[Release evidence E8](evidence/Evidence-Sources.md#e8)

## Research record and document releases

The Wiki is the current research source. The repository README is rendered
from this page and summarizes the same research state. An evidence release is
a frozen computation record; a document release is an immutable conference or
journal PDF produced from one reviewed Wiki revision when a submission is
needed. Routine Wiki updates do not rewrite archived PDFs. See the
[paper export contract](manuscript/Paper-Export-Contract.md).

## Models and measured-data scope

| Response | Forward model | Active parameters | Measured-data scope |
|---|---|---|---|
| Core-loss density | Isothermal Steinmetz law | `k`, `alpha`, `beta` | N49, N87, N95, and 3C95 temperature cohorts |
| Complex permeability | One-pole Cole--Cole law | `mu_s`, `f_rel`, `alpha_cc` | Accepted N87 and N95 LEA-MTB records |

Raw measured curves are not redistributed. Upstream file identities and
checksums are declared in the repository data manifest. The published evidence
projection contains only disclosure-safe aggregate and audit records.

## Read the research

| Need | Canonical page |
|---|---|
| Guided entry and complete directory | [Wiki index](overview/Index.md) |
| Current lifecycle state | [Project status](status/Project-Status.md) |
| Full methods and scientific argument | [Full manuscript](manuscript/Full-Manuscript.md) |
| Supported and unsupported claim language | [Claims and limits](claims/Claims-and-Limits.md) |
| Completed computations and comparator analysis | [Scientific job results](results/Scientific-Job-Results.md) |
| Numerical source map and hashes | [Evidence sources](evidence/Evidence-Sources.md) |
| Raw-to-aggregate verification | [Reproduce and audit](operations/Reproduce-and-Audit.md) |
| Conference and journal release rules | [Authoring and snapshots](manuscript/Authoring-and-Snapshots.md) |

## Verify the repository

Python 3.11 or newer is required for the validation environment.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
pytest
python wiki/build.py check
```

The validation suite checks implementation contracts, evidence bindings,
public-disclosure rules, navigation, README projection, and document-release
capability. Full MCMC and EIG campaigns use the pinned compute workflow.

## Repository map

| Path | Contents |
|---|---|
| [`wiki/`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/tree/main/wiki) | Canonical research narrative, claims, evidence map, and manuscript source |
| [`src/magcore_calib/`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/tree/main/src/magcore_calib) | Forward models, priors, inference, EIG, and diagnostics |
| [`experiments/`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/tree/main/experiments) | Scientific experiment entry points |
| [`configs/`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/tree/main/configs) | Models, samplers, acquisition policies, and seed contracts |
| [`results/`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/tree/main/results) | Published evidence projections and frozen releases |
| [`paper/`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/tree/main/paper) | Immutable conference and journal document releases |

Citation metadata are provided in `CITATION.cff`. Software is released under
the MIT License; upstream datasets retain their original licenses and
attribution requirements.
