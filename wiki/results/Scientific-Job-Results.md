---
title: Scientific Job Results
status: canonical computation ledger
last_updated: 2026-08-31
paper_source: false
---

# Scientific job results

The job ledger lists every scientific result family, including diagnostics
that do not support a headline claim. The release declares 213 tasks and 222
result artifacts. The rows below account for all 222 artifacts exactly; three
orchestration tasks produce no result artifact. [Source E1](../evidence/Evidence-Sources.md#e1)

## Complete result-artifact registry

| Scientific job family | Result artifacts | Publication status | Result or boundary | Source |
|---|---:|---|---|---|
| Matched-model recovery | 5 | Primary evidence | 28 of 30 nominal 90% coordinate intervals include the generating value; this is a small pipeline check, not calibration evidence | [E1](../evidence/Evidence-Sources.md#e1), [E2](../evidence/Evidence-Sources.md#e2) |
| Prior-offset sensitivity | 15 | Supporting diagnostic | Records retained; no general prior-robustness claim | [E1](../evidence/Evidence-Sources.md#e1) |
| Synthetic lot sensitivity | 5 | Supporting diagnostic | Target-valid synthetic records; no physical multi-lot claim | [E1](../evidence/Evidence-Sources.md#e1) |
| Local identifiability | 1 | Primary evidence | Local Fisher calculation has rank 6; local rank is not global physical uniqueness | [E1](../evidence/Evidence-Sources.md#e1), [E2](../evidence/Evidence-Sources.md#e2) |
| Estimator posterior states | 12 | Primary evidence | Twelve declared states used for score qualification | [E1](../evidence/Evidence-Sources.md#e1), [E3](../evidence/Evidence-Sources.md#e3) |
| Estimator score campaign | 122 | Primary evidence | Grid, reference, and doubled-budget score records | [E1](../evidence/Evidence-Sources.md#e1), [E3](../evidence/Evidence-Sources.md#e3) |
| Estimator downstream validation | 10 | Primary evidence | Raw-count and modeled-cost endpoints reproduced the reference endpoints | [E1](../evidence/Evidence-Sources.md#e1), [E3](../evidence/Evidence-Sources.md#e3) |
| Paired acquisition benchmark | 30 | Primary evidence | Eight policies, four primary direct contrasts, and no failure to reach the local gate | [E1](../evidence/Evidence-Sources.md#e1), [E4](../evidence/Evidence-Sources.md#e4) |
| Measured core-loss adequacy | 4 | Aggregate claim input | Four accepted in-sample fit records | [E1](../evidence/Evidence-Sources.md#e1), [E7](../evidence/Evidence-Sources.md#e7) |
| Measured permeability adequacy | 2 | Aggregate claim input | Two accepted in-sample fit records | [E1](../evidence/Evidence-Sources.md#e1), [E7](../evidence/Evidence-Sources.md#e7) |
| Excluded measured permeability | 2 | Excluded diagnostic | Two records are excluded by convergence or boundary checks | [E1](../evidence/Evidence-Sources.md#e1), [E7](../evidence/Evidence-Sources.md#e7) |
| Measured acquisition suggestions | 2 | Supporting diagnostic | Model-conditional suggestions; stable measured-data ranking is not claimed | [E1](../evidence/Evidence-Sources.md#e1) |
| Estimator sample matrices | 12 | Supporting | Flattened posterior samples supporting the estimator states | [E1](../evidence/Evidence-Sources.md#e1) |
| **Total** | **222** | Complete | Equal to the declared result-artifact count | [E1](../evidence/Evidence-Sources.md#e1) |

The three tasks without result artifacts are the smoke check, estimator-setting
selection, and final decision assembly. Their absence from the artifact total
is explicitly included in the accounting. [Source E1](../evidence/Evidence-Sources.md#e1)

## MM-1 work not included in the admitted artifact total

MM-1 declared 120 scenario--seed tasks (four fixed data generators by 30 new
seeds) followed by one validated aggregate task. The array closed with 119
validated records and one failed task marker. Because the complete matrix did
not pass the admission rule, the dependent aggregate was not created and no
policy, accuracy, coverage, or model-mismatch endpoint was admitted. These
diagnostic records are not part of the 213 completed tasks or 222 artifacts in
the validated release above. [Source E10](../evidence/Evidence-Sources.md#e10)

MM-2 independently declared another 120-task matrix using seeds 9100--9129
and a prospective sampler-escalation rule. It closed with 119 validated
records and one task-level sampler rejection. The aggregate was not created,
no endpoint was admitted, and these diagnostic records are not included in
either artifact total. [Source E11](../evidence/Evidence-Sources.md#e11)

## Policy endpoints

| Policy | Measurements to gate | Modeled cost to gate | Gate failures | Source |
|---|---:|---:|---:|---|
| Raw EIG | 5 in 30/30 seeds | Not its optimized endpoint | 0 | [E4](../evidence/Evidence-Sources.md#e4) |
| Raw predictive variance | 5 in 30/30 | 175 in 29 seeds; 180 in 1 | 0 | [E4](../evidence/Evidence-Sources.md#e4) |
| Raw Laplace D-optimality | 5 in 30/30 | 175 in 23 seeds; 180 in 7 | 0 | [E4](../evidence/Evidence-Sources.md#e4) |
| EIG per modeled cost | 6 in 30/30 | 190 in 29 seeds; 195 in 1 | 0 | [E4](../evidence/Evidence-Sources.md#e4) |
| Predictive variance per modeled cost | 5 in 30/30 | 175 in 30/30 | 0 | [E4](../evidence/Evidence-Sources.md#e4) |
| Laplace D-optimality per modeled cost | 6 in 30/30 | 190 in 29 seeds; 195 in 1 | 0 | [E4](../evidence/Evidence-Sources.md#e4) |
| Deterministic fixed channel-balanced traversal | 9 in 30/30 | 290 in 30/30 | 0 | [E4](../evidence/Evidence-Sources.md#e4) |
| Random channel-balanced traversal | Mean 7.8; range 5--13 | Mean 242.83; range 175--405 | 0 | [E4](../evidence/Evidence-Sources.md#e4) |

## Why EIG did not beat the strong comparators

### The raw policies meet the same discrete gate

Raw EIG, predictive variance, and Laplace D-optimality all reach the gate at
five measurements in every paired seed. This is a tie on the declared
measurement-count endpoint, not evidence that their rankings are equivalent.
Raw EIG and predictive variance have the same ordered acquisition sequence in
11 of 30 seeds and the same final selected set in 26 of 30. Raw EIG and
Laplace D-optimality have the same sequence in only 2 of 30, but the same final
set in 22 of 30. [Sources E4](../evidence/Evidence-Sources.md#e4) and
[E5](../evidence/Evidence-Sources.md#e5)

After four total measurements, none of the 30 seeds has passed both target
gates under any raw policy. Raw EIG still fails the (L_m) gate in 28 seeds;
predictive variance still fails the core-loss gate in 16 and the (L_m) gate
in 14; Laplace D-optimality still fails core loss in 21 and (L_m) in 9. At
measurement five, every raw policy passes both gates in every seed. The
policies therefore take different routes to the same small complementary set
of core-loss and permeability information, while the integer count-to-gate
endpoint removes the remaining utility differences. [Source E5](../evidence/Evidence-Sources.md#e5)

### Dividing by cost exposes an objective–gate mismatch

The cost-aware result is not a tie with predictive variance. EIG per cost uses
15 more modeled-cost units in 29 seeds and 20 more in one seed. The paired mean
penalty is 15.17 units with a 95% paired-bootstrap interval of 15.00--15.50
units; predictive variance wins all 30 pairs. [Source E4](../evidence/Evidence-Sources.md#e4)

The trajectory identifies the mechanism. At five measurements, the EIG/cost
policy has passed the (L_m) gate in 30 of 30 seeds but has passed the core-loss
gate in 0 of 30; predictive variance/cost has passed both in 30 of 30. EIG/cost
usually inserts (L_m(10\,\mathrm{kHz})) as its third adaptive acquisition
(28 of 30 seeds), whereas predictive variance/cost usually takes the decisive
(P_v(500\,\mathrm{kHz},0.2\,\mathrm T)) point then (29 of 30 seeds).
[Source E5](../evidence/Evidence-Sources.md#e5)

The comparison is even cleaner at the 22 paired states where both policies
have exactly the same observations after four measurements. The mean
core-loss interval half-width is 26.03%, still far above its 8% gate, while the
mean (L_m) half-width is 2.78%, already below its 5% gate. Nevertheless,
EIG/cost ranks the cheap 10 kHz (L_m) point first in 21 of those 22 states:
its mean information-per-cost utility is 0.05282 versus 0.04390 for the
high-leverage core-loss point. Predictive variance/cost ranks the core-loss
point first in all 22 shared states. [Source E5](../evidence/Evidence-Sources.md#e5)

This behavior is internally consistent. EIG/cost greedily maximizes joint
parameter information per modeled-cost unit; it does not minimize expected
cost remaining until two local predictive intervals cross their thresholds.
Once the (L_m) target is already precise, those objectives can disagree.
The defensible conclusion is therefore narrow: predictive variance/cost is
better for this exact cost-to-local-gate estimand in this finite matched-model
library. It does not establish universal predictive-variance superiority.

## Consequence for the next experiment

A fair follow-up should preregister a gate-aligned acquisition objective before
new outcomes are inspected. Candidates include target-weighted information
gain, probability of crossing the remaining gate, or approximate expected
cost-to-go. The current negative and tied results remain frozen; a new utility
must be reported as a new experiment, not substituted into this release.
