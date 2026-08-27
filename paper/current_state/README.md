# Archived full-paper render

This path predates the wiki publication workflow. Its name is retained to
avoid breaking historical links; it must not be interpreted as the current
version of the research.

[`manuscript.pdf`](manuscript.pdf) and [`source/`](source/) are a rendered
record. They are not edited to follow later wiki changes. The evidence identity
used by a rendered record belongs in [`results.lock.yaml`](results.lock.yaml),
while the current scientific manuscript and its active evidence binding are in
[`wiki/`](../../wiki/).

Future conference and journal documents must be generated from a reviewed
wiki commit with `python wiki/build.py snapshot`. The generated PDF and
`snapshot.json` are reviewed in staging and enter this directory only through
an explicit document-release commit.

The immutable six-page artifact remains separately archived as the
[`conference snapshot`](../conference_snapshot/README.md).
