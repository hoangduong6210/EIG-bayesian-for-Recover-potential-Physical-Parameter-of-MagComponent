---
title: Start Here
status: canonical onboarding
last_updated: 2026-09-15
paper_source: false
---

# Start Here

This project evaluates Bayesian calibration and sequential measurement
selection for Steinmetz core-loss and Cole--Cole permeability models. The
validated benchmark has 30 paired seeds, eight policies, and a frozen
disclosure-safe evidence projection.

A separate preregistered model-mismatch campaign now provides 120 validated
scenario--seed records. Its central result is negative: the local precision
gate can be reached while truth accuracy fails under the locked structural
departures. [Source E16](../evidence/Evidence-Sources.md#e16)

Read [Project Status](../status/Project-Status.md), [Current Claims](../claims/Current-Claim-Language.md),
[Dataset Registry](../datasets/Dataset-Registry.md), [Evidence Ledger](../evidence/Evidence-Ledger.md),
and [Limitations](../claims/Limitations.md). The safe repository check is:

```bash
python wiki/build.py check
pytest -q wiki/tests
```

The production release remains separate from the public projection because it
contains operational provenance. Do not promote an aggregate beyond the scope
declared by its evidence and claim records.
