# Magnetic-core Bayesian calibration and sequential design

This wiki is the living scientific manuscript for the Magnetic part of the
project. It is written for rapid technical review: the abstract and current
result are below, while the [full manuscript](Full-Manuscript.md) retains the
paper's complete methods, equations, citations, results, and limitations.

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

## How to read the project

1. [Project Status](Project-Status.md) gives the current evidence and open work.
2. [Full Manuscript](Full-Manuscript.md) is the canonical paper narrative.
3. [Claims and Limits](Claims-and-Limits.md) separates supported statements
   from prohibited interpretations.
4. [Reproduce and Audit](Reproduce-and-Audit.md) explains the evidence chain.
5. [Scientific Job Results](Scientific-Job-Results.md) accounts for every
   result artifact and explains the comparator outcome.
6. [Evidence Sources](Evidence-Sources.md) maps every result family to its
   machine-readable source.
7. [References](References.md) lists the scientific sources.
8. [Authoring and Snapshots](Authoring-and-Snapshots.md) defines how wiki
   changes become a two-column paper snapshot.

## Version boundary

The conference PDF is an immutable historical snapshot. The current PDF is
also a snapshot and may lag this wiki. Normal scientific-writing commits
modify only the wiki directory; the paper directory is regenerated only for
an explicit snapshot.
