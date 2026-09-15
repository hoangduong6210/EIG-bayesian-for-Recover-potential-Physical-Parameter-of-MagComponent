---
title: Reproduce and Audit
status: audit guide
last_updated: 2026-09-15
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

SparseMix-1 has a separate endpoint-free diagnostic asset containing all 18
task records and 18 deterministic thinned chains. After extraction, verify it
from the repository root with:

```bash
python scripts/public_sparse_mixing_bundle.py verify \
  --bundle sparsemix-1-20260831T054419Z_44edb519aa48
```

This verifies the portable file registry, task identities, hashes, array
contracts, and disclosure boundary. It cannot reconstruct full-chain
autocorrelation diagnostics from the thinned arrays; that audit requires a
rerun of the locked source and configuration. [Source E12](../evidence/Evidence-Sources.md#e12)

MM-3 has a separate result-bearing public asset. After downloading and
extracting `magcore-mm3-20260913-audit-v1.tar.gz`, run:

```bash
python scripts/public_model_mismatch_bundle.py verify \
  --bundle-dir mm3-20260913-audit-v1
```

The verifier checks all 120 public task hashes, reconstructs the registered
four-scenario × 30-seed matrix, validates every stored sampler decision, and
rebuilds every policy summary and paired contrast before comparing them with
the published aggregate. The task records contain checkpoint histories but no
full walker-by-iteration chains. [Source E16](../evidence/Evidence-Sources.md#e16)

The [scientific job ledger](../results/Scientific-Job-Results.md) accounts for all 222
result artifacts, and [Evidence Sources](../evidence/Evidence-Sources.md) gives the exact
JSON pointer for each quantitative result family. [Source E1](../evidence/Evidence-Sources.md#e1)

The exact commands for the current repository remain in
the experiment protocol, result-freezing guide, and public-audit guide under
the docs directory.
