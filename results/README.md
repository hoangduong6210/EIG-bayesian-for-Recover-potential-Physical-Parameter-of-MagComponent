# Public evidence release

`CURRENT` identifies the evidence release used by the manuscript. The
repository publishes the result summary, EIG convergence decision, generated
tables, and manuscript figures.

The compact published subset supports byte-level integrity checks and
manuscript-to-summary consistency. It does not by itself reconstruct the
reported aggregates from campaign-level trajectories and estimator records.
That stronger check requires the sanitized public audit bundle described in
[`docs/PUBLIC_AUDIT_BUNDLE.md`](../docs/PUBLIC_AUDIT_BUNDLE.md) or a complete
campaign rerun, which creates a new immutable release under
`results/frozen/<release-id>/`.
The archive descriptor for the current sanitized campaign projection is
[`audit/20260812T035654Z_a0703698ace9/asset.json`](audit/20260812T035654Z_a0703698ace9/asset.json).

The conference snapshot is backed separately by the allowlisted historical
bundle [`20260806T112202Z_9a37bcc67637`](historical/20260806T112202Z_9a37bcc67637/).
It is not selected by `CURRENT` and must not be combined with the present
30-seed result.

Verify the published subset with:

```bash
cd results/frozen/20260812T035654Z_a0703698ace9
sha256sum --check checksums.sha256
```
