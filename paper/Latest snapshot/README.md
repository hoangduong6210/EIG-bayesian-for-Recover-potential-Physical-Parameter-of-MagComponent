# Original journal snapshot: Bayesian calibration and sequential design

[Read the corrected journal paper](../journal-20260915-full-r1/main.pdf).
The [original journal PDF](main.pdf) remains archived here.

This 15-page journal manuscript presents joint Steinmetz–Cole–Cole calibration,
the paired acquisition benchmark, estimator qualification, measured-data model
adequacy, and the admitted structural-mismatch experiment. Its central result
is conditional: EIG improves on the fixed traversal but does not consistently
outperform strong comparators, and a narrow local posterior interval can remain
inaccurate under model mismatch.

| Document record | Value |
|---|---|
| Release | `journal-20260915-full` |
| Source Wiki commit | `a3e6326621d90123e5661c17e2d562fb0f5e0a41` |
| Format | A4, two columns |
| Contents | 5 figures, 8 tables, 49 references; 40 linked DOIs |
| Matched-model evidence | `20260817T072230Z_401e3030fe13` |
| Structural-mismatch evidence | `20260913T065150Z_a75d737c9d50` |
| Artifact registry | [snapshot.json](snapshot.json) |
| PDF SHA-256 | `ecd55c4f3d17146287cbb22140f82e41bfdadfc15403845634068a24f8c00e33` |

The paper was generated from the reviewed [Wiki manuscript](../../wiki/manuscript/Full-Manuscript.md),
not used as its source. Numerical evidence links in the PDF select the source
commit. This folder is an immutable document record despite its display name;
later research and future-work status belong in the
[research handoff](../../wiki/status/Research-Handoff.md).
The [conference snapshot](../conference_snapshot/README.md) and
[legacy full-paper render](../current_state/README.md) remain separate records.

## Verification and reproduction

From the repository root:

```bash
python wiki/build.py verify-snapshot --directory "paper/Latest snapshot"
```

This verifies the 19 registered output files and the input-manifest digest.
It does not independently authenticate the Git commit or rerun experiments.
The exact Wiki revision and input hashes are recorded in `snapshot.json`.
The archived TeX, bibliography, and figure assets can be compiled in a separate
copy of this directory with `latexmk -pdf main.tex`; routine Wiki changes do
not rebuild this record. PDF bytes may differ with the TeX distribution and
compilation timestamp.

Document verification and submission requirements are recorded in the
[research handoff](../../wiki/status/Research-Handoff.md#document-revision-and-submission-record).
