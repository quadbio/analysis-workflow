# Setting up and adopting

| | analysis repo | code repo |
| --- | --- | --- |
| create | `uvx cruft create https://github.com/quadbio/analysis_template` | `uvx cruft create https://github.com/scverse/cookiecutter-scverse` |
| managed with | pixi | uv |

`uvx cruft update` pulls template changes later, including the generic half of `REVIEW_GUIDE.md`. A code repo is
installed into the analysis environment as an editable path dependency of the root `pixi.toml`.

## Adopting the conventions in an existing analysis repo

1. Commit `.claude/settings.json` enabling `analysis-workflow@quadbio` (snippet: the plugin README). Remove
   repo-level copies of its hooks.
2. Add `analysis-workflow` to the root `pixi.toml`. Delete local copies of `task_paths`, `main_checkout`,
   `commit_adata` and `_task_template/`; leave their callers, which get fixed when next re-run.
3. `.gitignore`:
   ```gitignore
   data/
   figures/
   outputs/
   logs/
   *.zarr
   !analysis/**/results/**/*.csv
   !analysis/**/results/**/*.txt
   ```
   `figures/`, `outputs/` and `logs/` are unanchored so they match inside every task directory; the re-includes
   keep task evidence tracked where `*.csv`/`*.txt` are ignored globally.
4. Remove any notebook-output stripping (`nbstripout` in `.gitattributes`, its install step, its CI check).
5. Copy `assets/REVIEW_GUIDE.md`, adding the repo's own rules under its last heading.
6. In `AGENTS.md`, one short section naming the plugin and where the working objects live; delete restated rules.
7. Optionally `uvx cruft link https://github.com/quadbio/analysis_template` to receive template updates.
