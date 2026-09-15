---
title: Reproducibility
status: active runbook
last_updated: 2026-09-15
paper_source: false
---

# Reproducibility

Validated evidence release: `20260817T072230Z_401e3030fe13`; manifest SHA-256:
`85448a2c3c9db2db051c94543d8a336e7157d55289f10c1792e9c57d433812f7`.
The public projection is `evidence/results.json` and is checked by `build.py`.

The separate MM-3 evidence release contains 120 sanitized task records and is
bound to aggregate SHA-256
`03e8d81c48f3b5eb2c807a47b880972d3ea727b149788c2deffc35f1ac1d222d`.
Its raw-to-aggregate verifier and full audit boundary are documented under
[E16](../evidence/Evidence-Sources.md#e16).

```bash
python wiki/build.py check
pytest -q wiki/tests
```

The full reconstruction path and exporter command are documented in
[Reproduce and Audit](Reproduce-and-Audit.md). Snapshot creation additionally
requires the pinned Pandoc and LaTeX toolchain.
