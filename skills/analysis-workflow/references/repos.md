# Setting up and adopting

| | analysis repo | code repo |
| --- | --- | --- |
| template | `https://github.com/quadbio/analysis_template` | `https://github.com/scverse/cookiecutter-scverse` |
| managed with | pixi | uv |

`uvx cruft update` pulls template changes later, including the generic half of `REVIEW_GUIDE.md`.

## Creating a project

Ask the human for the project name, a one-line description, the author, and where the repos go (default: beside
their other repos). Then:

1. Analysis repo: `uvx cruft create <template> --no-input --extra-context '<json>'`, with the keys of the
   template's `cookiecutter.json`. In the new repo: `git init -b main` (before `pixi install`: the package takes
   its version from git), `pixi install`, `pixi run install-hooks`, `pixi run test`, a first commit.
2. Code repo, if the human wants one now: the same `cruft create` from its template, beside the analysis repo,
   then `git init -b main` and a first commit. Add it to the analysis repo's root `pixi.toml` as
   `<name> = { path = "../<name>", editable = true }` and re-run `pixi install`.
3. GitHub, only once the human confirms owner, name and visibility:
   `gh repo create <owner>/<name> --private --source . --push`.
4. The human starts a new session in the analysis repo: its settings, and with them this plugin's hooks, load at
   session start.

## Adopting the conventions in an existing analysis repo

1. Commit `.claude/settings.json` enabling `analysis-workflow@quadbio` (snippet: the plugin README); the hooks act
   only in repos that do. Remove repo-level copies of its hooks.
2. Add `analysis-workflow` to the root `pixi.toml`. Delete local copies of `task_paths`, `main_checkout`,
   `commit_adata` and `_task_template/`; leave their callers, which get fixed when next re-run.
3. `.gitignore`: add `*.zarr` and the template's blocks from `# Data never enters git` to the end. Their rules
   match inside every task directory, and their re-includes keep READMEs, placeholders and task evidence tracked.
4. Remove any notebook-output stripping (`nbstripout` in `.gitattributes`, its install step, its CI check).
5. Copy `assets/REVIEW_GUIDE.md`, adding the repo's own rules under its last heading.
6. In `AGENTS.md`, one short section naming the plugin and where the working objects live; delete restated rules.
7. Optionally `uvx cruft link https://github.com/quadbio/analysis_template` to receive template updates.
