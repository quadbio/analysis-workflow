# <task directory name, e.g. niches_v2>

**Date:** <YYYY-MM-DD, when the task started>

<!-- Every heading below stays, in this order, and no others are added; a section with nothing to say reads "None."
The guidance comments stay too. -->

<One or two sentences on what this task set out to answer. A later version names the one it follows and what it
changes.>

## Deliverables

<!-- Agreed with the human at the start, from the default unless they chose otherwise; a later change is recorded
here too. -->

| deliverable | where |
| --- | --- |
| <e.g. a figure> | `figures/<file>` (gitignored, in the main checkout) |
| <e.g. a write-back> | Write-back, below |

## Inputs

<!-- The actual files, not concepts: this is what makes the task re-runnable. -->

- Working object: `data/<dataset>/processed/.../<object>.zarr`, and the label keys used
- Other artifacts consumed: `analysis/<other_task>/outputs/<file>`, `data/<dataset>/processed/<file>`

## Write-back

<!-- What went into the working object, under which keys. Every key carries this directory's version, so it can be
traced back here by grepping the task READMEs. Anything promoted to `data/<dataset>/processed/` at sign-off is
recorded here with its final path. -->

- `obs["<name>_<version>"]`: one line on what it holds

## Running

<!-- From `scripts/`, on the main checkout's environment. Batch jobs get `MAIN=<main checkout>` at submit and log
to `PATHS.logs`. -->

```bash
PY="pixi run --manifest-path <main checkout>/pixi.toml --as-is python"
$PY 01_<step>.py
LOGS=$($PY -c "from _common import PATHS; print(PATHS.ensure().logs)")
```

## Jobs

<!-- Batch jobs this session launched, counted at the end. -->

| queue | launched | succeeded | failed | cancelled |
| --- | --- | --- | --- | --- |
| <queue> | <n> | <n> | <n> | <n> |

## PRs and issues

<!-- Every PR and issue this session opened, in any repo, added when opened, with a short summary of each; the
details are in the PR. -->

- `<owner/repo>#<n>`: one or two lines on what it did
