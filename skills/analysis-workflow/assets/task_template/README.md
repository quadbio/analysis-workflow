# <task name, matching this directory>

**Date:** <YYYY-MM-DD, when the task started>

One or two sentences on what this task set out to answer. A later version names the one it follows and what it
changes.

## Deliverables

Agreed with the human at the start; a later change is agreed and recorded here too.

| deliverable | where |
| --- | --- |
| <e.g. a report> | `reports/<file>` |
| <e.g. a write-back> | Write-back, below |

## Inputs

Name the actual files, not concepts: this is what makes the task re-runnable.

- Working object: `data/<dataset>/processed/.../<object>.zarr`, and the label keys used
- Other artifacts consumed: `analysis/<other_task>/outputs/<file>`, `data/<dataset>/processed/<file>`

## Decisions

Load-bearing parameters, what was tried and rejected, and the diagnostics that changed the method. A decision not
yet taken has the value `open`.

| decision | value | by | why |
| --- | --- | --- | --- |
| <what> | <the choice> | <human or agent, YYYY-MM-DD> | <the evidence, e.g. a file in `results/`> |

## Write-back

What went into the working object, and under which keys. The version in this directory's name appears in every
key, so a key can be traced back here by grepping the task READMEs.

- `obs["<name>_<version>"]`: one line on what it holds
- `obsm["X_<name>_<version>"]`: likewise

Anything promoted to `data/<dataset>/processed/` at sign-off is recorded here with its final path.

## Running

From the task directory, on the main checkout's environment. Batch jobs get `MAIN=<main checkout>` at submit and
log to `PATHS.logs`:

```bash
PY="pixi run --manifest-path <main checkout>/pixi.toml --as-is python"
$PY scripts/<step>.py
LOGS=$($PY -c "from _common import PATHS; print(PATHS.ensure().logs)")
```

## PRs and issues

Every PR and issue this session opened, in any repo, added when opened.

- `<owner/repo>#<n>`: one line on what it is
