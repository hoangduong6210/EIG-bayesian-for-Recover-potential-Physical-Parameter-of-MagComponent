---
title: Research Handoff and Future Work
status: current phase closed; successor work unregistered
last_updated: 2026-09-15
paper_source: false
---

# Research handoff and future work

## Closeout boundary

The current phase concludes with a qualified synthetic acquisition pipeline,
a paired comparison with strong policies, measured-data adequacy checks, and
the admitted MM-3 discrepancy campaign. The scientific conclusion is narrower
than the initial acquisition motivation: EIG reduces the local gate count
against the fixed traversal, does not consistently outperform the strong
comparators, and can reach that gate while making inaccurate predictions
under the specified mismatch. The evidence and limitations remain part of the
result, including negative comparisons.
[Sources E4](../evidence/Evidence-Sources.md#e4),
[E7](../evidence/Evidence-Sources.md#e7), and
[E16](../evidence/Evidence-Sources.md#e16)

The journal snapshot `journal-20260915-full` is archived in
`paper/Latest snapshot`, exported from reviewed Wiki revision
`a3e6326621d90123e5661c17e2d562fb0f5e0a41`. Its 15-page PDF contains five figures,
eight tables and 49 references. The 19-file output registry passed checksum
verification; the PDF SHA-256 is
`ecd55c4f3d17146287cbb22140f82e41bfdadfc15403845634068a24f8c00e33`.
The source revision precedes this closeout entry: document and Wiki versions
are intentionally distinct. The release manifest determines the exact
evidence, figures, bibliography and PDF. The folder name is not an instruction to update an existing snapshot
in place. Later research changes belong in the Wiki; a later submission needs
another explicit document release. The Wiki remains the canonical scientific
source. See [authoring and snapshots](../manuscript/Authoring-and-Snapshots.md).

Closure does not authorize another compute campaign. Proposed work below has
no admitted outcomes, and closure must not be described as completion of
laboratory validation or uncertainty calibration.

## Reading order for a successor

| Step | Read | Decision supported |
|---|---|---|
| 1 | [Home](../Home.md), [project status](Project-Status.md) | Scope and current conclusion |
| 2 | [Full manuscript](../manuscript/Full-Manuscript.md), [claims and limits](../claims/Claims-and-Limits.md) | Model, estimands, and permissible claims |
| 3 | [Scientific job ledger](../results/Scientific-Job-Results.md), [evidence sources](../evidence/Evidence-Sources.md) | Exact result-bearing artifacts and source pointers |
| 4 | [MM-3 protocol](../experiments/Model-Mismatch-V3-Preregistration.md), [SparseMix-2](../experiments/Sparse-Mixing-V2-Preregistration.md) | Prospective criteria and sampler admission history |
| 5 | [Reproduce and audit](../operations/Reproduce-and-Audit.md), [research workflow](../operations/Research-Workflow.md) | Verification before reuse or a new run |
| 6 | [Decision 0001](../decisions/0001-gate-aligned-objective.md), the register below | What requires a new protocol |

The [index](../overview/Index.md) provides the full page directory. Literature
citations establish background, whereas evidence labels identify results
produced by this project. A successor should trace both before changing a
scientific statement.

## Evidence to preserve

| Record | Identity and disposition | Reuse boundary |
|---|---|---|
| Matched-model freeze | `20260817T072230Z_401e3030fe13`; admitted, [E8](../evidence/Evidence-Sources.md#e8) | Retain original seeds, costs, gate, estimator decision, and direct contrasts |
| Selection overlap | Post hoc diagnostic, [E9](../evidence/Evidence-Sources.md#e9) | Explains observed decisions; not a new confirmatory comparator trial |
| MM-1 and MM-2 | Closed without admitted aggregates, [E10](../evidence/Evidence-Sources.md#e10), [E11](../evidence/Evidence-Sources.md#e11) | Do not pool partial records into a successor endpoint analysis |
| Sampler qualification | Endpoint-free pilot and independent SparseMix-2 confirmation, [E13](../evidence/Evidence-Sources.md#e13), [E14](../evidence/Evidence-Sources.md#e14) | Qualification of the locked sparse states, not a universal mixing guarantee |
| MM-3 | `20260913T065150Z_a75d737c9d50`; admitted, [E16](../evidence/Evidence-Sources.md#e16) | Preserve the registered matrix, all eight policies, and discrepancy definitions |

The matched-model and MM-3 public assets are separate. Their manifests and
hashes, rather than a mutable `CURRENT` pointer, select the evidence. MM-3
provides sanitized task records, scores, trajectories, and sampler checkpoint
histories, but no full walker-by-iteration chains. Its verifier reconstructs
aggregates and checks recorded diagnostic decisions; it cannot independently
recalculate autocorrelation times from absent chains. Full-chain diagnostic
reproduction requires a new execution of the locked workflow.
[Sources E8](../evidence/Evidence-Sources.md#e8) and
[E16](../evidence/Evidence-Sources.md#e16)

## Verification before continuation

From the repository root, activate the project environment with Python 3.11
or newer and the test dependencies installed, then run:

```bash
python wiki/build.py check
python -m pytest -q wiki/tests
python -m pytest -q
```

Use the same interpreter for the builder and tests; an unrelated system
`pytest` may select an older Python. These checks validate repository
contracts; they do not rerun the research
campaigns. Download the release assets identified by the evidence ledger and
follow [Reproduce and audit](../operations/Reproduce-and-Audit.md) to verify
the stored-record-to-aggregate chain. Record the source revision, configuration
hash, dependency versions, and evidence identities before any rerun. Do not
replace an admitted artifact with a newly generated file under the same
identity.

For a new study, first create a separate protocol with fresh seeds, exact
policy and task matrices, diagnostic and failure rules, endpoints, and
aggregation code. Retain rejection diagnostics and state whether full chains
will be archived. Review the protocol before inspecting its outcomes. An
incomplete task matrix remains non-admitted unless the prospectively fixed
analysis explicitly defines a valid incomplete-data treatment.

## Future-work register

All entries below are proposed and unregistered at phase closure. The order
separates a new acquisition objective from inference checks and subsequent
physical validation; no row changes the completed studies retrospectively.

| Workstream | Motivation | Entry requirement | Evidence needed before a new claim |
|---|---|---|---|
| Gate-aligned utility | Joint parameter information need not minimize time to the two-target gate | Freeze the utility, target weights or crossing objective, shared outcomes, separate count/cost evaluations, and fresh seeds | Paired comparisons with EIG and the existing strong policies; include gate failures, holdout error, and false confidence, not only earlier gate crossing |
| Matched-model SBC | A narrow interval and an MCMC gate do not establish inference calibration | Freeze a prior-predictive simulation protocol, parameter transformations, posterior sampling budget, rank construction, and rejection handling | Rank and coverage diagnostics with Monte Carlo uncertainty and dependence checks; no claimed calibration from a few recovery examples |
| Discrepancy-aware coverage | MM-3 exposes inaccurate confidence outside the fitted family | Define discrepancy families, held-out domains, and any model/noise extensions before new outcomes | Separate coverage, predictive error, and false-confidence results; distinguish these from standard matched-model SBC |
| Measured-model adequacy | Large loss-permeability residuals limit physical interpretation | Prespecify candidate model extensions, geometry/noise treatment, and held-out measurements | Improved held-out performance and uncertainty checks across channels; in-sample fit improvement alone is insufficient |
| Measured acquisition ranking | Estimator qualification on synthetic states is not a measured ranking guarantee | Establish adequate measured posterior states, stable design keys, and a replicated scoring protocol | Budget-convergence and ranking-stability results, including near ties and estimator uncertainty, conditional on the validated model |
| Laboratory savings and transfer | Modeled cost is not elapsed laboratory time | Controlled measurement protocol, repeated lots or components, recorded setup/acquisition overhead, and comparable budgets | Paired measured timing and predictive-quality outcomes; report failures and overhead before asserting practical savings |

Global six-parameter identification is not an automatic consequence of any
row. A dedicated study must specify parameter-recovery tolerances,
identifiability checks, joint uncertainty criteria, and external prediction
requirements. Likewise, superiority over strong comparators requires new
paired evidence; it cannot be inferred from the original fixed-traversal
comparison.

## Conditions for reopening the phase

A successor should name a responsible maintainer, choose a question from the
register, and obtain agreement on a new protocol and compute scope. Update the
Wiki status to distinguish registered, running, rejected, and admitted work.
Publish source-linked results and limitations after verification. Build a new
paper only when another document snapshot is requested; do not use an edited
PDF as the source of the next Wiki revision.
