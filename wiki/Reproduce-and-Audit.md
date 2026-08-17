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

## Public boundary

Production records can contain machine-specific paths and scheduler metadata.
They are not committed directly. A public audit bundle must first project only
scientific records, remove operational metadata, pass disclosure scanning, and
verify independently.

The exact commands for the current repository remain in
the experiment protocol, result-freezing guide, and public-audit guide under
the docs directory.
