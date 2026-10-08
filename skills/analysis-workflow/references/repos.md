# Setting up and adopting

## A new analysis repo

```bash
uvx cruft create https://github.com/quadbio/analysis_template
```

Then follow the generated README. The template already carries everything below. `uvx cruft update` later pulls
template changes, including the generic half of `REVIEW_GUIDE.md`.

## A new code repo

```bash
uvx cruft create https://github.com/scverse/cookiecutter-scverse
```

Install it into the analysis repo's environment as an editable path dependency of the root `pixi.toml`:
`mypackage = { path = "../mypackage", editable = true }`.

## Adopting the conventions in an existing analysis repo

1. **Plugin.** Commit `.claude/settings.json` with the marketplace and `"enabledPlugins":
   {"analysis-workflow@quadbio": true}` (snippet in the plugin README). Remove any repo-level copies of these hooks.
2. **Package.** Add `analysis-workflow` to the root `pixi.toml` (git tag, or an editable path to a checkout). Delete
   any local implementation of `task_paths`/`main_checkout`/`commit_adata`, and any `_task_template/`. Leave
   their callers alone: an old task gets its import fixed when it is next re-run.
3. **`.gitignore`.**
   ```gitignore
   data/
   figures/
   outputs/
   logs/
   *.zarr
   # task evidence is tracked even where *.csv / *.txt are ignored globally
   !analysis/**/results/**/*.csv
   !analysis/**/results/**/*.txt
   ```
   `figures/`, `outputs/` and `logs/` are unanchored on purpose: they match inside every task directory.
4. **Notebook outputs are committed.** Remove any output-stripping filter (an `nbstripout` entry in
   `.gitattributes`, its install step, a CI check that rejects outputs).
5. **`REVIEW_GUIDE.md`.** Copy `assets/REVIEW_GUIDE.md` and append the repo's own rules under its last heading.
   Point `AGENTS.md` at it.
6. **`AGENTS.md`.** One short section naming the plugin and saying where this repo's working objects live.
   Delete restatements of rules the skill owns; keep the repo's facts (datasets, environments, companion packages).
7. Optionally `uvx cruft link https://github.com/quadbio/analysis_template` to receive template updates.
