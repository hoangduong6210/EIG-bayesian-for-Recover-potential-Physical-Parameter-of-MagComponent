---
title: Paper Export Contract
status: canonical publication policy
last_updated: 2026-08-19
paper_source: false
---

# Paper Export Contract

The wiki and document releases have independent versions. The wiki contains
the active manuscript, claim language, and evidence binding. A document release
is an immutable conference or journal export made from one reviewed wiki
revision when a submission or circulation artifact is required.

The only allowed source direction is:

```text
reviewed wiki revision -> staged export -> approved document snapshot
```

Editing generated TeX or a PDF and copying the change back into the wiki is not
part of the workflow. Routine wiki commits do not compile or refresh archived
documents.

An export may use only admitted claims with resolved evidence and limitations.
Its `snapshot.json` records the document kind and release name, source wiki
commit and input hashes, evidence release and projection digests, figure and
bibliography inputs, and generated-file hashes. The build output must be staged
outside the repository. After scientific and layout review, the approved
artifact enters `paper/` in a dedicated document-release commit.

A later result or prose revision creates another named snapshot. Conference
and journal records already under `paper/` are never rewritten to follow the
wiki.
