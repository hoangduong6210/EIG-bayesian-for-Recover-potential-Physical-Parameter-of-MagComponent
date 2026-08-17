# Authoring and Paper Snapshots

## Source-of-truth rule

The wiki directory is the living manuscript. Scientific-writing commits
normally change only files under this directory. Generated LaTeX and PDF files
are not updated for every prose edit.

The GitHub Wiki, once initialized, is a one-way mirror of this directory. It
must not become a second authoring source.

## Normal edit

1. Edit the relevant wiki page.
2. Run the wiki build tool in check mode.
3. Review the diff for claim scope, citations, and internal disclosure.
4. Commit only the wiki directory.

## Explicit snapshot

Only when a version is approved for circulation:

1. Select an immutable evidence release by exact ID and manifest digest.
2. Update the manuscript manifest in the wiki.
3. Run the wiki build tool in snapshot mode with a staging directory.
4. Review the staged two-column A4 PDF, citations, figures, page footer, and
   snapshot manifest.
5. Copy the approved staged artifact into the current paper snapshot in a
   dedicated snapshot commit.

The build never writes into the paper directory unless a human explicitly
performs the final snapshot step. The conference snapshot remains immutable.
