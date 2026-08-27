# Comparator selection-path diagnostic

This directory contains the compact aggregate from a descriptive analysis of
the 30 benchmark-v4 acquisition trajectories. The analysis was defined after
the primary comparator result and is not a preregistered superiority test.

Reproduce the complete JSON and CSV output from an independently verified
release with:

```bash
python scripts/analyze_selection_overlap.py \
  --release-dir <verified-20260817-release> \
  --output-dir <new-empty-directory>
```

The tracked aggregate is
[`20260817T072230Z_401e3030fe13/aggregate_summary.json`](20260817T072230Z_401e3030fe13/aggregate_summary.json),
SHA-256 `cbdfc7f19a707ed9e58d3fb129ddcd314c1b75e1447eaa1ebdf88f75b07b6153`.
The 30 sanitized source trajectories are available in the
[public audit release v2](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/releases/tag/evidence-20260817-audit-v2).
