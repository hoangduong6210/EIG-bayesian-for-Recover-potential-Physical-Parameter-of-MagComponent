---
title: Wiki Index Compatibility Page
status: navigation annex
last_updated: 2026-08-19
paper_source: false
---

# Wiki index

This index is the entry point for readers who did not participate in the
project. Choose the question closest to what you need; each row points first to
the human-readable explanation and then, where applicable, to the exact
evidence record.

## Recommended reading path

| Reader goal | Start here | What to read next | Outcome |
|---|---|---|---|
| Understand the project quickly | [Home](Home.md) | [Project Status](Project-Status.md) | Current conclusion, evidence scope, and unfinished work |
| Evaluate the scientific argument | [Full Manuscript](Full-Manuscript.md) | [Claims and Limits](Claims-and-Limits.md) | Methods, results, citations, and the exact boundary of each claim |
| Inspect completed computations | [Scientific Job Results](Scientific-Job-Results.md) | [Evidence Sources](Evidence-Sources.md) | Complete result-artifact ledger and source pointer for every reported result family |
| Reproduce or audit a result | [Reproduce and Audit](Reproduce-and-Audit.md) | [`evidence/results.json`](evidence/results.json) | Evidence chain, release identity, hashes, and machine-readable values |
| Create a paper version | [Authoring and Snapshots](Authoring-and-Snapshots.md) | [Full Manuscript](Full-Manuscript.md) | Rules for producing an explicit two-column snapshot without changing the historical conference version |
| Check literature support | [References](References.md) | [`bibliography/references.bib`](bibliography/references.bib) | Human-readable references and the bibliography records used in the manuscript |

## Find an answer by scientific question

| Question | Human-readable answer | Exact result source |
|---|---|---|
| What is the current defensible conclusion? | [Home — Current conclusion](Home.md#current-conclusion) | [E4 — paired endpoints](Evidence-Sources.md#e4) |
| Did EIG beat predictive variance or D-optimality? | [Job Results — Why EIG did not beat the strong comparators](Scientific-Job-Results.md#why-eig-did-not-beat-the-strong-comparators) | [E4 — direct contrasts](Evidence-Sources.md#e4), [E5 — trajectories](Evidence-Sources.md#e5) |
| Why did EIG/cost lose to predictive variance/cost? | [Job Results — Objective–gate mismatch](Scientific-Job-Results.md#dividing-by-cost-exposes-an-objectivegate-mismatch) | [E5 — shared-state utilities](Evidence-Sources.md#e5) |
| How will structural model mismatch be tested? | [MM-1 preregistration](experiments/Model-Mismatch-Preregistration.md) | `configs/model_mismatch.toml` |
| Which jobs completed and which are diagnostic only? | [Complete result-artifact registry](Scientific-Job-Results.md#complete-result-artifact-registry) | [E1 — campaign accounting](Evidence-Sources.md#e1) |
| Is six-parameter identification established? | [Claims and Limits](Claims-and-Limits.md) | [E2 — recovery](Evidence-Sources.md#e2), [E6 — secondary endpoints](Evidence-Sources.md#e6) |
| How stable is the nested EIG estimator? | [Full Manuscript — Nested-estimator qualification](Full-Manuscript.md#nested-estimator-qualification) | [E3 — estimator qualification](Evidence-Sources.md#e3) |
| How good are predictions away from the stopping targets? | [Full Manuscript — Disjoint holdout](Full-Manuscript.md#disjoint-holdout-and-six-parameter-endpoints) | [E6 — holdout aggregates](Evidence-Sources.md#e6) |
| Does the model fit measured magnetic data? | [Project Status — Measured-data adequacy](Project-Status.md#measured-data-adequacy) | [E7 — measured adequacy](Evidence-Sources.md#e7) |
| Can the result be called laboratory-time saving? | [Claims and Limits — Not supported](Claims-and-Limits.md#not-supported) | [E4 — modeled-cost endpoint](Evidence-Sources.md#e4) |
| Which release produced the numbers? | [Project Status](Project-Status.md) | [E8 — release integrity](Evidence-Sources.md#e8) |

## Page directory

| Page | Role | Use it when |
|---|---|---|
| [Home](Home.md) | Executive scientific summary | You need the main result without reading methods |
| [Project Status](Project-Status.md) | Current research state | You need completed work, numerical endpoints, or next experiments |
| [Full Manuscript](Full-Manuscript.md) | Complete paper narrative | You need the full methods, equations, literature, results, and discussion |
| [Claims and Limits](Claims-and-Limits.md) | Claim-control ledger | You need to decide whether a proposed sentence is supported |
| [Scientific Job Results](Scientific-Job-Results.md) | Computation and result ledger | You need job-family status, artifact accounting, or comparator interpretation |
| [Evidence Sources](Evidence-Sources.md) | Evidence map | You need a JSON pointer, checksum, or source scope for a number |
| [Reproduce and Audit](Reproduce-and-Audit.md) | Verification workflow | You need to follow the chain from configuration to frozen aggregate |
| [References](References.md) | Literature index | You need the scientific source behind a model or method |
| [Authoring and Snapshots](Authoring-and-Snapshots.md) | Publication workflow | You need to edit the wiki or create a paper snapshot |
| [MM-1 preregistration](experiments/Model-Mismatch-Preregistration.md) | Prospective experiment protocol | You need the fixed model-mismatch scenarios, seeds, endpoints, or admission rule |

## How to verify a number

1. Follow the visible source label beside the number, such as
   [E4](Evidence-Sources.md#e4).
2. Read the source scope and JSON pointer on [Evidence Sources](Evidence-Sources.md).
3. Open [`evidence/results.json`](evidence/results.json) and navigate to that
   pointer.
4. Confirm the projection and release hashes shown on the evidence page.
5. For deeper reconstruction, follow [Reproduce and Audit](Reproduce-and-Audit.md).

If a result-bearing statement has no evidence label, treat it as unverified
until the source is added. Literature citations support scientific background;
E1--E9 labels support numerical results from this project.
