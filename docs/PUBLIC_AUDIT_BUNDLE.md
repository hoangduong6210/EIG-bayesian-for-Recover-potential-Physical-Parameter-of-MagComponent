# Public raw-to-aggregate audit bundle

The compact frozen directory authenticates the tables, figures, and summary
used by the current manuscript. A separate public audit projection is used for
campaign-record inspection because the production archive also contains
machine paths, scheduler metadata, environment dumps, and operational logs
that are neither scientific inputs nor appropriate public material.

## Audit scope

The projection contains the scientific dependency graph for the reported
acquisition endpoint and EIG-estimator validation:

| Record class | Count | Purpose |
|---|---:|---|
| Paired acquisition trajectories | 30 | Reconstruct count, modeled cost, win, failure, reduction, and paired-bootstrap summaries |
| Estimator posterior states | 12 | Identify the fixed posterior states used in convergence testing |
| Candidate-score records | 108 | Inspect the 27 estimator settings across 12 states |
| Reference-score records | 12 | Compare candidate settings with the prespecified reference |
| Doubled-budget score records | 2 | Audit the two prespecified numerical sentinels |
| Downstream validation records | 10 | Verify endpoint stability on held-out synthetic seeds |
| Estimator decisions | 2 | Trace score inputs to the selected setting and downstream decision |
| Retained posterior-sample matrices | 12 | Recompute estimator scores from the retained flattened samples |
| Published aggregate | 1 | Compare reconstructed acquisition statistics with the manuscript input |

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
                         30 acquisition trajectories
                                      |
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

Verification fails closed on undeclared or escaping paths, source or public
checksum mismatches, nonfinite JSON values, malformed posterior archives,
machine-identifying material, broken state-to-score-to-decision references,
broken downstream references, incomplete common-outcome pairing, or any
difference between reconstructed and published acquisition statistics.

## Publication policy

The records projection and posterior matrices should be released as separate
versioned archival assets rather than added to Git history. Their small root
manifests and digests may be tracked here. A changed transformation profile or
scientific record creates a new asset version; published assets are never
overwritten in place.

The complete v1 projection for the current evidence release is published as
[`magcore-public-audit-20260812-v1.tar.zst`](https://github.com/hoangduong6210/EIG-bayesian-for-Recover-potential-Physical-Parameter-of-MagComponent/releases/download/evidence-20260812-audit-v1/magcore-public-audit-20260812-v1.tar.zst).
Its archive and root-manifest digests, byte size, and scope flags are locked in
[`results/audit/20260812T035654Z_a0703698ace9/asset.json`](../results/audit/20260812T035654Z_a0703698ace9/asset.json).
