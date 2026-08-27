# Document-release snapshots

The scientific manuscript is authored in [`wiki/`](../wiki/). This directory
contains rendered records made for a particular circulation or submission;
it is not an editable manuscript source and it does not define the current
scientific state.

| Record | Role | Evidence boundary |
|---|---|---|
| [`conference_snapshot/`](conference_snapshot/) | Immutable six-page conference record | Historical release `20260806T112202Z_9a37bcc67637` |
| [`current_state/`](current_state/) | Legacy full-paper render retained under its original path | Read its local lock; do not infer currency from the directory name |

New conference or journal documents are exported from a reviewed wiki commit
into a staging directory. An approved export is then archived here in a
dedicated snapshot commit. Routine wiki changes neither rebuild nor modify an
existing PDF.

For the current result and argument, use the
[`full wiki manuscript`](../wiki/Full-Manuscript.md). Historical numbers must
be interpreted through the metadata stored beside the corresponding PDF.
