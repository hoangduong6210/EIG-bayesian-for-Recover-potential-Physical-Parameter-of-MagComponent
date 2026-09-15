---
title: Decision 0001 - Separate Information Gain from Gate-Aligned Utility
status: accepted decision
date: 2026-08-19
last_updated: 2026-09-15
paper_source: false
---

# Decision 0001: Separate information gain from gate-aligned utility

EIG optimizes joint parameter information, while the evaluated stopping rule
asks when two predictive intervals cross thresholds. Their objectives can
disagree. A target-weighted, crossing-probability, or cost-to-go utility must be
preregistered as a new experiment; it cannot retroactively replace the frozen
EIG benchmark.

MM-3 now supplies the prospective motivation for that experiment: every
policy reached the width gate in every registered scenario, while combined-
mismatch raw EIG was false-confident in 22/30 seeds. This result does not select
or tune the next utility. Candidate utilities, evaluation endpoints, seed
namespace and acceptance criteria must be frozen before new outcomes are
generated. [Source E16](../evidence/Evidence-Sources.md#e16)
