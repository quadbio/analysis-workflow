# <task name, matching this directory>

**Date:** <YYYY-MM-DD, when the task started>

One or two sentences on what this task set out to answer.

## Inputs

Name the actual files, not concepts: this is what makes the task re-runnable.

- Working object: `data/<dataset>/processed/.../<object>.zarr`, and the label keys used
- Other artifacts consumed: `analysis/<other_task>/outputs/<file>`, `data/<dataset>/processed/<file>`

## Outputs

| what | where |
| --- | --- |
| evidence tables | `results/` (tracked) |
| report | `reports/` (tracked) |
| figures | `figures/` (gitignored, in the main checkout) |
| data artifacts | `outputs/` (gitignored, in the main checkout) |

## Write-back

What went into the working object, and under which keys. The version in this directory's name appears in every
key, so a key can be traced back here by grepping the task READMEs.

- `obs["<name>_<version>"]`: one line on what it holds
- `obsm["X_<name>_<version>"]`: likewise

Anything promoted to `data/<dataset>/processed/` at sign-off is recorded here with its final path.

## Running

From the task directory, on the main checkout's environment. Batch jobs log to `PATHS.logs`:

```bash
PY="pixi run --manifest-path <main checkout>/pixi.toml python"
$PY scripts/<step>.py
LOGS=$($PY -c "from _common import PATHS; print(PATHS.ensure().logs)")
```

## Notes

Decisions a reader would otherwise have to reverse-engineer: what was tried and rejected, which parameters are
load-bearing, what is still provisional.
