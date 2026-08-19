---
title: Reproducibility
status: active runbook
last_updated: 2026-08-19
paper_source: false
---

# Reproducibility

Validated evidence release: `20260817T072230Z_401e3030fe13`; manifest SHA-256:
`85448a2c3c9db2db051c94543d8a336e7157d55289f10c1792e9c57d433812f7`.
The public projection is `evidence/results.json` and is checked by `build.py`.

```bash
python wiki/build.py check
pytest -q wiki/tests
```

The full reconstruction path and exporter command are documented in
[Reproduce and Audit](Reproduce-and-Audit.md). Snapshot creation additionally
requires the pinned Pandoc and LaTeX toolchain.
