---
title: Research Wiki Index
status: canonical index
last_updated: 2026-08-26
paper_source: false
---

# Research Wiki index

This directory routes each question to one canonical page. Numerical statements
use evidence labels E1--E9; the evidence page records the corresponding JSON
pointer, scope, release identity, and checksum.

## Recommended reading paths

| Reader goal | Start | Continue | Outcome |
|---|---|---|---|
| Understand the project quickly | [Home](../Home.md) | [Project status](../status/Project-Status.md) | Current conclusion, evidence scope, and unfinished work |
| Evaluate the scientific argument | [Full manuscript](../manuscript/Full-Manuscript.md) | [Claims and limits](../claims/Claims-and-Limits.md) | Methods, results, citations, and claim boundaries |
| Inspect completed computations | [Scientific job results](../results/Scientific-Job-Results.md) | [Evidence sources](../evidence/Evidence-Sources.md) | Artifact accounting and source pointers |
| Reproduce or audit a result | [Reproduce and audit](../operations/Reproduce-and-Audit.md) | [Evidence ledger](../evidence/Evidence-Ledger.md) | Configuration-to-aggregate verification chain |
| Prepare a submission | [Authoring and snapshots](../manuscript/Authoring-and-Snapshots.md) | [Paper export contract](../manuscript/Paper-Export-Contract.md) | Named conference or journal document release |
| Join the project | [Start here](Start-Here.md) | [Contributing](../governance/Contributing.md) | Terminology, checks, and contribution boundaries |

## Find an answer by scientific question

| Question | Explanation | Evidence or protocol |
|---|---|---|
| What is defensible now? | [Current claims](../claims/Current-Claim-Language.md) | [Claims and limits](../claims/Claims-and-Limits.md) |
| Did EIG beat predictive variance or D-optimality? | [Comparator results](../results/Scientific-Job-Results.md#why-eig-did-not-beat-the-strong-comparators) | [E4](../evidence/Evidence-Sources.md#e4), [E5](../evidence/Evidence-Sources.md#e5), [E9](../evidence/Evidence-Sources.md#e9) |
| Is six-parameter identification established? | [Limitations](../claims/Limitations.md) | [E2](../evidence/Evidence-Sources.md#e2), [E6](../evidence/Evidence-Sources.md#e6) |
| How stable is the nested EIG estimator? | [Estimator qualification](../manuscript/Full-Manuscript.md#nested-estimator-qualification) | [E3](../evidence/Evidence-Sources.md#e3) |
| How well does the model fit measured data? | [Measured-data adequacy](../status/Project-Status.md#measured-data-adequacy) | [E7](../evidence/Evidence-Sources.md#e7) |
| Which release produced the numbers? | [Project status](../status/Project-Status.md) | [E8](../evidence/Evidence-Sources.md#e8) |
| What happened in the first structural-mismatch campaign? | [MM-1 closeout](../experiments/Model-Mismatch-Preregistration.md#closeout) | [E10](../evidence/Evidence-Sources.md#e10) |
| What is fixed for the independent successor? | [MM-2 preregistration](../experiments/Model-Mismatch-V2-Preregistration.md) | [`configs/model_mismatch_v2.toml`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/blob/main/configs/model_mismatch_v2.toml) |

## Complete page directory

| Area | Canonical pages |
|---|---|
| Orientation | [Home](../Home.md), [Start here](Start-Here.md), [Glossary](Glossary.md) |
| Architecture | [Research system map](../architecture/Research-System-Map.md) |
| Methods | [Sequential design method](../methods/Sequential-Design-Method.md) |
| Data | [Dataset registry](../datasets/Dataset-Registry.md) |
| Experiments | [MM-1 protocol and closeout](../experiments/Model-Mismatch-Preregistration.md), [MM-2 preregistration](../experiments/Model-Mismatch-V2-Preregistration.md) |
| Results | [Scientific results](../results/Scientific-Results.md), [Scientific job results](../results/Scientific-Job-Results.md) |
| Claims | [Current claims](../claims/Current-Claim-Language.md), [Claims and limits](../claims/Claims-and-Limits.md), [Limitations](../claims/Limitations.md), [Historical claims](../claims/Historical-Claim-Ledger.md) |
| Evidence | [Evidence ledger](../evidence/Evidence-Ledger.md), [Evidence sources](../evidence/Evidence-Sources.md) |
| Status | [Project status](../status/Project-Status.md) |
| Decisions | [Decision 0001](../decisions/0001-gate-aligned-objective.md) |
| Reproduction | [Reproducibility](../operations/Reproducibility.md), [Reproduce and audit](../operations/Reproduce-and-Audit.md), [Research workflow](../operations/Research-Workflow.md) |
| References | [References](../references/References.md), [Technical source map](../references/Technical-Source-Map.md) |
| Manuscript | [Full manuscript](../manuscript/Full-Manuscript.md), [Authoring and snapshots](../manuscript/Authoring-and-Snapshots.md), [Paper export contract](../manuscript/Paper-Export-Contract.md) |
| Governance | [Contributing](../governance/Contributing.md), [License and assets](../governance/License-and-Assets.md) |

## Verify a number

1. Follow the evidence label beside the number.
2. Read its scope and JSON pointer on [Evidence sources](../evidence/Evidence-Sources.md).
3. Open [`evidence/results.json`](../evidence/results.json) or the separately
   bound E9 diagnostic named by the source record.
4. Confirm the projection and release hashes.
5. Follow [Reproduce and audit](../operations/Reproduce-and-Audit.md) for the
   raw-to-aggregate chain.

If a result-bearing sentence lacks an evidence label, treat it as unverified.
Literature citations support scientific background; E1--E9 support numerical
results produced by this project.
