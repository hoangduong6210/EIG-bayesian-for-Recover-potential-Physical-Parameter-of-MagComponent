# Public evidence release

`CURRENT` identifies the evidence release used by the manuscript. The
repository publishes the result summary, EIG convergence decision, generated
tables, and manuscript figures.

The published files are sufficient to verify every numerical statement in the
current manuscript. A complete campaign rerun creates a new immutable release
under `results/frozen/<release-id>/`.

The conference snapshot is backed separately by the allowlisted historical
bundle [`20260806T112202Z_9a37bcc67637`](historical/20260806T112202Z_9a37bcc67637/).
It is not selected by `CURRENT` and must not be combined with the present
30-seed result.

Verify the published subset with:

```bash
cd results/frozen/20260812T035654Z_a0703698ace9
sha256sum --check checksums.sha256
```
