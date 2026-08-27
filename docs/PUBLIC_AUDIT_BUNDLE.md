# Public raw-to-aggregate audit bundle

The compact frozen directory authenticates the tables, figures, and summary
used by the current manuscript. A separate public audit projection is used for
campaign-record inspection because the production archive also contains
machine paths, scheduler metadata, environment dumps, and operational logs
that are neither scientific inputs nor appropriate public material.

## Audit scope

The v2 projection contains the scientific dependency graph for the reported
acquisition endpoints, direct comparator contrasts, secondary validation, and
EIG-estimator validation:

| Record class | Count | Purpose |
|---|---:|---|
| Paired acquisition trajectories | 30 | Reconstruct all eight policies, direct contrasts, count/cost endpoints, and point-level secondary validation |
| Estimator posterior states | 12 | Identify the fixed posterior states used in convergence testing |
| Candidate-score records | 108 | Inspect the 27 estimator settings across 12 states |
| Reference-score records | 12 | Compare candidate settings with the prespecified reference |
| Doubled-budget score records | 2 | Audit the two prespecified numerical sentinels |
| Downstream validation records | 10 | Verify endpoint stability on held-out synthetic seeds |
| Estimator decisions | 2 | Trace score inputs to the selected setting and downstream decision |
| Retained posterior-sample matrices | 12 | Recompute estimator scores from the retained flattened samples |
| Published aggregate | 1 | Compare reconstructed acquisition statistics with the manuscript input |

Each v4 trajectory record also retains the 23 prespecified holdout point rows
for every policy. Verification recomputes per-channel point counts, relative
RMSE, median absolute relative error, and latent 90% interval coverage from
those rows before comparing the per-seed summaries and cross-seed aggregate.

The retained sample matrices have shape `240000 × 6`. They are flattened
posterior draws used by the estimator study, not walker- and iteration-indexed
raw MCMC chains.

Raw measured curves are not included. The audit bundle therefore reconstructs
the paired matched-model acquisition result and estimator-validation chain; it
does not independently reproduce the measured-data fits or establish a
laboratory-optimal policy.

## Sanitized dependency graph

```text
retained posterior samples
           |
           v
12 posterior-state records
           |
           v
122 candidate-score records
           |
           v
static estimator decision
           |
           v
10 downstream validations --> final estimator decision
                                      |
                                      v
                   30 eight-policy acquisition trajectories
                         /             |              \
                        v              v               v
              primary EIG      direct comparator   point-level
                endpoints         contrasts       secondary checks
                         \             |              /
                                      v
                          published acquisition summary
```

Every transformed JSON file carries both its public SHA-256 digest and the
source digest recorded by the immutable production manifest. Cross-record
paths and hashes are recalculated after sanitization; original hashes are not
reused for transformed content.

## Export and verification

The source release must already pass its immutable manifest. Export refuses to
overwrite a destination and copies only allowlisted scientific records:

```bash
python scripts/public_audit_bundle.py export \
  --source-release /path/to/immutable-release \
  --destination /path/to/public-audit-release
```

For a smaller records-only asset, omit the posterior matrices:

```bash
python scripts/public_audit_bundle.py export \
  --source-release /path/to/immutable-release \
  --destination /path/to/public-audit-records \
  --without-samples
```

Verify either projection with:

```bash
python scripts/public_audit_bundle.py verify \
  --bundle /path/to/public-audit-release
```

New exports use `magnetic-public-audit/2.0`. The verifier remains compatible
with the already published `magnetic-public-audit/1.0` asset; v1 is verify-only
and is never emitted by a new export.

Verification fails closed on undeclared or escaping paths, source or public
checksum mismatches, nonfinite JSON values, malformed posterior archives,
machine-identifying material, broken state-to-score-to-decision references,
broken downstream references, incomplete common-outcome pairing, a mixed or
incomplete v4 seed/policy registry, stale point-level holdout summaries, stale
paired endpoints, or any difference between reconstructed primary, direct
comparator, secondary-validation, and published acquisition statistics.

## Publication policy

The records projection and posterior matrices should be released as separate
versioned archival assets rather than added to Git history. Their small root
manifests and digests may be tracked here. A changed transformation profile or
scientific record creates a new asset version; published assets are never
overwritten in place.

The v2 projection for evidence release `20260817T072230Z_401e3030fe13` is
published in two scopes: a records-only archive for ordinary audit work and a
larger archive containing the twelve retained posterior-sample matrices. The
release URLs, archive digests, root-manifest digests, byte sizes, and scope
flags are locked in
[`results/audit/20260817T072230Z_401e3030fe13/asset.json`](../results/audit/20260817T072230Z_401e3030fe13/asset.json).

The earlier v1 archive remains available as historical evidence. Its descriptor
is [`results/audit/20260812T035654Z_a0703698ace9/asset.json`](../results/audit/20260812T035654Z_a0703698ace9/asset.json).
