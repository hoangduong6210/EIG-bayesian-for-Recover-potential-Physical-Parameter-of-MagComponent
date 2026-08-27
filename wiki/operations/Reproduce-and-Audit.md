---
title: Reproduce and Audit
status: audit guide
last_updated: 2026-08-19
paper_source: false
---

# Reproduce and Audit

The evidence chain is:

**preregistered configuration → per-state posterior diagnostics → per-seed
eight-policy trajectories → reconstructed paired endpoints → aggregate summary
→ immutable freeze → sanitized public audit asset → paper snapshot**

## Audit guarantees

- Policy order cannot alter candidate noise or state-level MCMC seeds.
- Every trajectory adds exactly one valid unrevealed candidate per step.
- Every acquisition state carries sampler diagnostics and validity.
- Count, modeled cost, gate status, holdout metrics, and parameter endpoints
  are reconstructed from raw policy records before aggregation.
- A freeze is accepted only when all 30 seeds, all eight policies, all four
  direct contrasts, and all evidence hashes satisfy the declared contract.
  [Sources E1](../evidence/Evidence-Sources.md#e1), [E4](../evidence/Evidence-Sources.md#e4), and
  [E8](../evidence/Evidence-Sources.md#e8)

## Public boundary

Production records can contain machine-specific paths and execution metadata.
They are not committed directly. The current
[disclosure-safe result projection](../evidence/results.json) contains the
scientific aggregates used by this wiki. Public audit bundle v2 provides all
30 sanitized acquisition trajectories and the estimator decision chain; its
larger asset adds the twelve flattened posterior-sample matrices. Both assets
remove operational metadata, pass disclosure scanning, and verify against
their published manifests. [Source E8](../evidence/Evidence-Sources.md#e8)

The [scientific job ledger](../results/Scientific-Job-Results.md) accounts for all 222
result artifacts, and [Evidence Sources](../evidence/Evidence-Sources.md) gives the exact
JSON pointer for each quantitative result family. [Source E1](../evidence/Evidence-Sources.md#e1)

The exact commands for the current repository remain in
the experiment protocol, result-freezing guide, and public-audit guide under
the docs directory.
