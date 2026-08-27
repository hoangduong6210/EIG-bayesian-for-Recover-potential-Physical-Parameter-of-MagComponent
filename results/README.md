# Evidence releases

An evidence release, a wiki revision, and a document release are different
objects:

- `results/frozen/<release-id>/` is an immutable computation freeze;
- [`wiki/manuscript.toml`](../wiki/manuscript.toml) selects evidence for the
  active scientific manuscript;
- `paper/<document-release>/` archives a conference or journal snapshot and
  retains the evidence identity selected when it was rendered.

`CURRENT` is an operator convenience for local result work. It is not a
document selector, and changing it must not rewrite an existing PDF. Production
freezes can contain machine and scheduler provenance and must not be published
directly.

The disclosure-safe release procedure is documented in
[`PUBLIC_AUDIT_BUNDLE.md`](../docs/PUBLIC_AUDIT_BUNDLE.md). Public bundles are
distributed outside Git history with a checked descriptor and archive digest.
The repository may retain descriptors for older bundles without treating them
as the current wiki evidence. A compact aggregate subset does not by itself
reconstruct the raw-to-aggregate calculation; that audit level requires the
corresponding sanitized record bundle.

The conference document is backed separately by the allowlisted historical
bundle [`20260806T112202Z_9a37bcc67637`](historical/20260806T112202Z_9a37bcc67637/).
Its five-seed result must not be combined with later matched-model campaigns.
