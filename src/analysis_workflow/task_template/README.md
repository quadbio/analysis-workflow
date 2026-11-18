# <task directory name, e.g. human_niches_v2>

**Date:** <YYYY-MM-DD, when the task started>
**Author:** <a human's initials, or the model, e.g. Claude Opus 5.5>
**Id:** <set by `analysis-workflow new`; shared stores record under it what this task wrote>

<!-- Every heading below stays, in this order, and no others are added; a section with nothing to say reads "None."
The guidance comments stay too. -->

<One or two sentences on what this task set out to answer. A later version names the one it follows and what it
changes.>

## Deliverables

<!-- What the task delivers. An agent agrees them with the human at the start, from the default unless they chose
otherwise; a later change is recorded here too. -->

| deliverable | where |
| --- | --- |
| <e.g. a figure> | `figures/<file>` (gitignored, in the main checkout) |
| <e.g. a write-back> | Write-back, below |

## Write-back

<!-- What each key written to a shared object holds, and the final path of anything placed in
`data/<dataset>/processed/`. Which task wrote a key is recorded in the store itself. -->

- `obs["<key>"]`: one line on what it holds

## Running

<!-- The notebooks in `notebooks/` and scripts in `scripts/`, in run order, on the main checkout's environment. Batch
jobs get `MAIN=<main checkout>` at submit and log to `PATHS.logs`. -->

```bash
PY="pixi run --manifest-path <main checkout>/pixi.toml --as-is python"
$PY 01_<step>.py
LOGS=$($PY -c "from _common import PATHS; print(PATHS.ensure().logs)")
```

## Jobs

<!-- Batch jobs this task launched, counted at the end. -->

| queue | launched | completed | failed | cancelled |
| --- | --- | --- | --- | --- |
| <queue> | <n> | <n> | <n> | <n> |

## PRs and issues

<!-- Every PR and issue this task opened, in any repo, added when opened, with a short summary of each; the details
are in the PR. -->

- `<owner/repo>#<n>`: one or two lines on what it did
