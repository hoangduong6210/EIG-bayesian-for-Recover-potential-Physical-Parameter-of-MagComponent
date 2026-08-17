# Magnetic-core Bayesian calibration and sequential design

This study evaluates Bayesian calibration and sequential measurement selection
for Steinmetz core-loss and Cole--Cole permeability models. The
[full manuscript](Full-Manuscript.md) gives the methods, equations, citations,
results, and limitations.

Authors: Viet Hoang Duong, Viet Huy Duong, and Lun-Min Shih.

## Current conclusion

The latest validated 30-paired-seed matched-model benchmark does **not** show
that EIG is better than the strong acquisition comparators.

- Raw EIG, predictive variance, and Laplace D-optimality all reached the local
  two-target precision gate in five measurements in every paired seed.
  [Source E4](Evidence-Sources.md#e4)
- EIG per modeled cost tied Laplace D-optimality, but predictive variance was
  better in all 30 seeds by a mean modeled cost of 15.17 units.
  [Source E4](Evidence-Sources.md#e4)
- Raw EIG still improved over the specified deterministic fixed traversal
  (five versus nine measurements), but that is a baseline-specific result.
  [Source E4](Evidence-Sources.md#e4)
- No result is a measured laboratory-time saving or validation on a real
  magnetic component.

The trajectory-level reason for the tie and loss is documented in
[Why EIG did not beat the strong comparators](Scientific-Job-Results.md#why-eig-did-not-beat-the-strong-comparators).

## How to find information

| If you want to... | Open | You will find |
|---|---|---|
| Understand the result quickly | [Project Status](Project-Status.md) | Current evidence, numerical endpoints, and next work |
| Read the paper argument | [Full Manuscript](Full-Manuscript.md) | Methods, equations, citations, results, and limitations |
| Check what can be claimed | [Claims and Limits](Claims-and-Limits.md) | Supported wording and prohibited interpretations |
| See every completed result family | [Scientific Job Results](Scientific-Job-Results.md) | Complete artifact ledger and comparator explanation |
| Verify a reported number | [Evidence Sources](Evidence-Sources.md) | Evidence label, JSON pointer, scope, and checksum |
| Reproduce the evidence chain | [Reproduce and Audit](Reproduce-and-Audit.md) | Configuration-to-freeze verification workflow |

The [complete Wiki Index](Wiki-Index.md) also provides reading paths by
reader type, a question-to-answer lookup table, a page directory, and a
step-by-step procedure for verifying any number.

Paper-version history and rendering instructions are kept separately in
[Authoring and Snapshots](Authoring-and-Snapshots.md).
