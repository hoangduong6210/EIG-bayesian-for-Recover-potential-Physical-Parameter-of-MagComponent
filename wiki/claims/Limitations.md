---
title: Limitations
status: canonical
last_updated: 2026-09-15
paper_source: false
prose_reviewed: true
claim_ids: C-EIG-RAW-001, C-EIG-COST-001, C-FIXED-001, C-RECOVERY-001, C-ADEQ-001, C-MM3-GATE-001
---

# Limitations

1. The primary benchmark is matched-model synthetic and uses a finite,
   isothermal, 37-design library.
2. The endpoint is a local two-target precision gate, not global parameter
   identification or a universally optimal laboratory plan.
3. Modeled cost is not measured time or financial cost.
4. Five recovery seeds do not establish empirical uncertainty calibration.
5. The one-pole measured permeability model shows substantial loss-component
   discrepancy and does not justify stable measured-data acquisition ranking.
6. MM-3 evaluates only three fixed synthetic structural departures. Its poor
   truth accuracy and holdout inclusion do not quantify arbitrary mismatch or
   measured-material robustness. [Source E16](../evidence/Evidence-Sources.md#e16)
7. All MM-3 policies reach the local width gate, so gate attainment alone does
   not validate prediction accuracy under discrepancy. [Source E16](../evidence/Evidence-Sources.md#e16)
8. MM-3 stores checkpoint diagnostics but not full walker-by-iteration chains;
   independent recomputation of autocorrelation and acceptance requires a
   locked rerun. [Source E16](../evidence/Evidence-Sources.md#e16)
9. Multi-lot variability and component-level validation remain future work.
