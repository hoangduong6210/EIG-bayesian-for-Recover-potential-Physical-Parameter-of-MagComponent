---
title: Start Here
status: canonical onboarding
last_updated: 2026-08-19
paper_source: false
---

# Start Here

This project evaluates Bayesian calibration and sequential measurement
selection for Steinmetz core-loss and Cole--Cole permeability models. The
validated benchmark has 30 paired seeds, eight policies, and a frozen
disclosure-safe evidence projection.

Read [Project Status](status/Project-Status.md), [Current Claims](claims/Current-Claim-Language.md),
[Dataset Registry](datasets/Dataset-Registry.md), [Evidence Ledger](evidence/Evidence-Ledger.md),
and [Limitations](LIMITATIONS.md). The safe repository check is:

```bash
python wiki/build.py check
pytest -q wiki/tests
```

The production release remains separate from the public projection because it
contains operational provenance. Do not promote an aggregate beyond the scope
declared by its evidence and claim records.
