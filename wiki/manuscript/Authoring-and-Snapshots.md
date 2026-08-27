---
title: Authoring and Paper Snapshots
status: publication guide
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
2. Run `python wiki/build.py write-readme` to refresh the repository summary.
3. Run the wiki build tool in check mode.
4. Review the diff for claim scope, citations, and internal disclosure.
5. Commit the Wiki and README change without rebuilding `paper/`.

## Hosted Wiki projection

The organized source tree is flattened before publication so page names and
links remain stable on GitHub Wiki. After committing a reviewed Wiki revision,
stage the allowlisted projection outside the repository:

```bash
python wiki/build.py stage-wiki --output /tmp/magnetic-public-wiki
```

The command strips source metadata, rewrites local links, copies declared
assets, checks the staged link graph, and writes `publish-manifest.json` with
the source commit and file hashes. Publish that directory to the separate Wiki
repository only after the GitHub Wiki has been initialized and the projection
has been reviewed.

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
