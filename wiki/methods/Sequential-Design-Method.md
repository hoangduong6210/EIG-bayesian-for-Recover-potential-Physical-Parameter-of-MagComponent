---
title: Bayesian Sequential Design Method
status: canonical method
last_updated: 2026-08-19
paper_source: false
prose_reviewed: true
claim_ids: C-EIG-RAW-001, C-EIG-COST-001, C-FIXED-001, C-RECOVERY-001
---

# Bayesian Sequential Design Method

The benchmark compares raw and cost-normalized EIG, predictive variance,
Laplace D-optimality, deterministic fixed traversal, and random balanced
traversal. Within each seed, policies share truth and candidate outcomes.
Posterior diagnostics are checked at every acquisition state. Primary endpoints
are measurements or modeled cost to the local two-target gate; direct contrasts
use paired bootstrap intervals and win/tie/loss counts.
