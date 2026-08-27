---
title: Research Wiki Source Tree
status: source-tree guide
last_updated: 2026-08-26
paper_source: false
---

# Research Wiki source tree

`Home.md` is the canonical current-research summary and the prose source for
the repository README. `manuscript/Full-Manuscript.md` is the sole source for
conference and journal document releases. Other pages own one scientific or
operational concern each.

| Directory | Responsibility |
|---|---|
| `overview/` | Onboarding, directory, and terminology |
| `status/` | Current lifecycle state |
| `architecture/`, `methods/`, `datasets/` | Scientific system, method, and data definitions |
| `experiments/`, `results/` | Prospective protocols and admitted outcomes |
| `claims/`, `evidence/` | Defensible language, limitations, source records, and hashes |
| `decisions/` | Prospective methodological decisions |
| `operations/` | Reproduction, audit, and compute workflow |
| `references/` | Literature and technical source mapping |
| `manuscript/` | Paper source and release contract |
| `governance/` | Contribution, license, and asset rules |

Use the [Wiki index](overview/Index.md) to navigate the research. Validate any
change with:

```bash
python wiki/build.py write-readme
python wiki/build.py check
pytest -q wiki/tests
```

The hosted Wiki, when enabled, is built as a flat allowlisted projection. The
organized source tree is not mirrored directly.
