# Bayesian calibration and sequential design for magnetic-core models

[Read the journal paper](main.pdf)

This manuscript evaluates joint Steinmetz–Cole–Cole calibration and sequential
measurement selection using matched-model recovery, paired policy comparisons,
measured-data adequacy checks and controlled structural mismatch. EIG improves
on the fixed traversal but does not consistently outperform strong comparators;
local posterior precision does not ensure accurate prediction under mismatch.

| Document record | Value |
|---|---|
| Release | `journal-20260915-full-r1` |
| Source Wiki commit | `927bbcb6d0b862598fae87d2575a872bbd79b5f1` |
| Contents | 14 pages, two columns; 5 figures, 8 tables, 49 references |
| Matched-model evidence | `20260817T072230Z_401e3030fe13` |
| Structural-mismatch evidence | `20260913T065150Z_a75d737c9d50` |
| Artifact registry | [snapshot.json](snapshot.json) |
| PDF SHA-256 | `4407294f5203998cb68ce7f14ce9f507fc722ac32ca25482dd070407125cd255` |

This editorial revision clarifies data availability and removes discussion of
conference publication status from the scientific body. Numerical results,
figure assets and bibliography are unchanged from the
[original journal snapshot](<../Latest snapshot/README.md>).
The [Wiki manuscript](../../wiki/manuscript/Full-Manuscript.md) remains the
scientific source; the [handoff](../../wiki/status/Research-Handoff.md) records
future work and submission requirements.

From the repository root, verify the archived files without rebuilding:

```bash
python wiki/build.py verify-snapshot --directory paper/journal-20260915-full-r1
```

The TeX, bibliography and assets can be compiled in a separate copy of this
directory with `latexmk -pdf main.tex`. The snapshot registry binds the output
files and source inputs; it does not rerun the scientific experiments.
