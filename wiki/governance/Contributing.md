---
title: Contributing to the Research Wiki
status: canonical governance
last_updated: 2026-08-19
paper_source: false
---

# Contributing to the Research Wiki

Each record has an assigned location: claim wording in `claims/`, computed
values in `evidence/` and `results/`, data scope in `datasets/`, lifecycle in
`status/`, decisions in `decisions/`, and publication rules in `manuscript/`.
All pages carry front matter. The full manuscript alone is eligible for paper
export.

Update the evidence projection and its hashes before changing a quantitative
claim. Preserve ties, losses, exclusions, and model inadequacy. Run the wiki
contract and tests before review.

Every scientific change must include a detailed update to the canonical Wiki
in the same commit: the question, method or protocol change, execution status,
evidence paths and checksums, limitations, and next decision. New readers must
be able to retrieve that record through the Index. A submitted job is not a
completed result; a completed computation is not an admitted scientific claim.
The README is regenerated from the Wiki after a research-state change. Routine
updates do not rebuild or replace document-release snapshots.
