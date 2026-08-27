---
title: Authoring and Paper Snapshots
status: publication annex
last_updated: 2026-08-19
paper_source: false
---

# Authoring and Paper Snapshots

## Editing rule

Edit manuscript text under `wiki/`. Do not update generated LaTeX or PDF files
for ordinary prose changes. If the hosted GitHub Wiki is enabled, publish from
this directory and do not edit the hosted copy independently.

Wiki revisions and document releases use separate version histories. The wiki
describes the current research; a PDF describes only the reviewed wiki revision
and evidence release named in its snapshot record.

## Normal edit

1. Edit the relevant wiki page.
2. Run the wiki build tool in check mode.
3. Review the diff for claim scope, citations, and internal disclosure.
4. Commit the wiki change without rebuilding `paper/`.

## Paper release

Only when a conference or journal version is approved for circulation:

1. Select an immutable evidence release by exact ID and manifest digest.
2. Update and review the manuscript manifest in the wiki, then commit it.
3. Run the wiki build tool in snapshot mode with a release kind, stable release
   name, and staging directory outside the repository. For example:

   ```bash
   python wiki/build.py snapshot \
     --document-kind journal \
     --release-name journal-example-2026 \
     --output /tmp/journal-example-2026
   ```

4. Review the staged two-column A4 PDF, citations, figures, page footer, and
   snapshot manifest.
5. Copy the approved staged artifact into a newly named directory under
   `paper/` in a dedicated document-release commit.

The build stages output outside the paper directory. Copy an approved PDF and
its `snapshot.json` into `paper/` only as a named release. Do not alter a
submitted conference or journal record.
