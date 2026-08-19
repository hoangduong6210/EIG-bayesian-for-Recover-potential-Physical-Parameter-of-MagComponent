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

## Normal edit

1. Edit the relevant wiki page.
2. Run the wiki build tool in check mode.
3. Review the diff for claim scope, citations, and internal disclosure.
4. Commit only the wiki directory.

## Paper release

Only when a version is approved for circulation:

1. Select an immutable evidence release by exact ID and manifest digest.
2. Update the manuscript manifest in the wiki.
3. Run the wiki build tool in snapshot mode with a staging directory.
4. Review the staged two-column A4 PDF, citations, figures, page footer, and
   snapshot manifest.
5. Copy the approved staged artifact into the current paper snapshot in a
   dedicated snapshot commit.

The build stages output outside the paper directory. Copy an approved PDF and
its manifest into `paper/` only as a named release. Do not alter the submitted
conference record.
