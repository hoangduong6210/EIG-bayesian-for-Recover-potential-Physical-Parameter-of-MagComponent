# Claims-to-evidence register

Status values are `not supported`, `descriptive`, or `supported`. The quantitative
entries below are bound to the immutable estimator-validation and acquisition
release `20260812T035654Z_a0703698ace9` by
`paper/current_state/results.lock.yaml`. The acquisition
claims are restricted to the paired matched-model experiment and the local
two-target precision gate; they are not laboratory-efficiency claims.

| Claim | Status now | Required frozen evidence |
|---|---|---|
| The framework calibrates Steinmetz and Cole--Cole parameters | descriptive | Model/config definitions and successful pipeline smoke report |
| Active parameter combinations have a reported Fisher condition number | supported | Full-rank $6\times6$ local Fisher spectrum with declared scaling; Fig. 1(a) |
| Synthetic parameters are recovered within a stated tolerance | supported | Five matched-model seeds, per-parameter errors and interval inclusion; Table 1 and Fig. 1(b) |
| Raw EIG uses fewer measurements than the fixed channel-balanced traversal | supported | Thirty paired confirmatory seeds: 4--5 versus 9 measurements, 44.8% mean paired reduction, 95% bootstrap interval 4.00--4.10 measurements for the paired difference, 100% win rate, and zero gate failures; audited reference estimator |
| EIG/cost reduces total modeled acquisition cost | supported | Thirty paired confirmatory seeds: 34.4% mean paired reduction in prespecified modeled cost, 95% bootstrap interval 34.31%--34.48%, 100% win rate, and zero gate failures; not measured laboratory time |
| Measured complex-permeability fit has stated RMS errors | supported | Convergence-valid LEA_MTB per-component in-sample RMS metrics; Fig. 2(b) |
| Measured core-loss fit has stated exponents and RMS errors | supported | Filter-audited per-material fit records and in-sample RMS metrics; Fig. 2(b) |
| Performance is robust to prior-center offsets | not supported | E4 recovery and predictive metrics for every declared offset/seed |
| Injected lot effects can be separated in simulation | not supported | E7 synthetic task metrics; manuscript label must say synthetic |

## Claims not supported by the present evidence

- “Calibrated uncertainty” without an empirical coverage experiment.
- Physical lot-to-lot separation based on synthetic injections.
- Temperature-dependent loss prediction from a temperature-independent model.
- Full Jiles--Atherton or DC hysteresis-loop identification.
- A new converter topology or converter-control contribution.
- Replacement of HALT, qualification, or physical testing.
- Cost and schedule savings without traceable cost/time studies.
- Accurate magnetic-component identification from a two-target precision gate.
- A validated optimal laboratory plan from model-conditional measured-data EIG.
- Causal explanations for measured-data mismatch without a diagnostic comparison.

## Evidence release

The tracked frozen subset provides checksum integrity and
manuscript-to-summary traceability. Raw trajectory-to-acquisition-summary
reconstruction is a separate audit level, defined by
[`PUBLIC_AUDIT_BUNDLE.md`](PUBLIC_AUDIT_BUNDLE.md). The versioned audit asset is
published separately from Git history; the compact subset must still not be
described as a complete campaign-record archive.

Locked evidence-manifest SHA-256:
`c5a6b05e1ab84b3f8b72a40be1480148c360889b6142884c44cf9e35df219dc0`.

| Manuscript evidence | Frozen artifact | SHA-256 |
|---|---|---|
| Numerical statements in Results Sections 7.1--7.3 | `results/frozen/20260812T035654Z_a0703698ace9/tables/paper_summary.json` | `9e1dc314ea22c0da17a48b19a8f9333a876be3064de80af63fbc2bb5e20570e6` |
| Generated value macros | `results/frozen/20260812T035654Z_a0703698ace9/tables/frozen_result_macros.tex` | `52300e019970c657216f5c3cffdcbb3ae68bd2e04900d9c01f8982a8bcdfd35e` |
| Recovery table | `results/frozen/20260812T035654Z_a0703698ace9/tables/frozen_results.tex` | `75ae746fea2559cb99c688e70aca6dd6ae7be6c2177b4796047e89e29b5fa5a5` |
| Figure 1: Fisher spectrum and matched-model recovery | `results/frozen/20260812T035654Z_a0703698ace9/figures/synthetic_results.pdf` | `eda32a615684d6b9b0e90be67150f0e190bd69989a369be4f000e0275a25e854` |
| Figure 2: paired acquisition and measured model adequacy | `results/frozen/20260812T035654Z_a0703698ace9/figures/acquisition_measured_results.pdf` | `efcb58f042960a4b14e35e1fedd73ae3a3dff388c814f958f67ce2b421e665bc` |

Estimator validation evaluated 27 candidate budgets across 12 fixed posterior states. No cheaper
grid cell passed every raw-EIG and EIG/cost gate, so the prespecified verified
reference `(1200 outer, 400 inner, 40 replicates)` was selected. Against the
doubled-budget audit, the minimum paired-bootstrap selector agreement was
0.9985 for raw EIG and 1.0000 for EIG/cost; minimum Spearman correlations were
0.9983 and 0.9992, interval-overlap minima were 0.8710, and relative regret was
zero. Both downstream objectives matched the reference on all ten held-out seeds.

Measured-data EIG rankings are intentionally not claimed: the repeated-estimator audit did not support a stable ranking. N87 and 3C95 MagNet permeability fits are retained as excluded diagnostics and are not used in numerical claims.
