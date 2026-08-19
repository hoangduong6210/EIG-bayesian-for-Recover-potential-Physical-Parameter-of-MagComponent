---
title: Decision 0001 - Separate Information Gain from Gate-Aligned Utility
status: accepted decision
date: 2026-08-19
paper_source: false
---

# Decision 0001: Separate information gain from gate-aligned utility

EIG optimizes joint parameter information, while the evaluated stopping rule
asks when two predictive intervals cross thresholds. Their objectives can
disagree. A target-weighted, crossing-probability, or cost-to-go utility must be
preregistered as a new experiment; it cannot retroactively replace the frozen
EIG benchmark.
