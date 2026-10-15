# Setting up and adopting

| | analysis repo | code repo |
| --- | --- | --- |
| template | `https://github.com/quadbio/analysis_template` | `https://github.com/scverse/cookiecutter-scverse` |
| managed with | pixi | uv |

The analysis template's README says how to create a project from it and update it later.

## Creating a project

Ask the human for the answers to the template's prompts (its `cookiecutter.json`) and where the repos go (default:
beside their other repos). Then:

1. Analysis repo: the template README's steps, with `--no-input --extra-context '<json>'` for the answers.
2. Code repo, if the human wants one now: the same `cruft create` from its template, beside the analysis repo,
   then `git init -b main` and a first commit. Add it to the analysis repo's root `pixi.toml` as
   `<name> = { path = "../<name>", editable = true }` and re-run `pixi install`.
3. GitHub, only once the human confirms owner, name and visibility.
4. The human starts a new session in the analysis repo: its settings, and with them this plugin's hooks, load at
   session start.

## Adopting the conventions in an existing analysis repo

1. Merge the template's `.claude/settings.json` into the repo's and commit it; the hooks act only in repos that
   enable the plugin. Remove repo-level copies of its hooks.
2. Add the template's `analysis-workflow` dependency to the root `pixi.toml`. Delete local copies of `task_paths`,
   `main_checkout`, `commit_adata` and `_task_template/`; leave their callers, which get fixed when next re-run.
   Take `FilePaths.ROOT` from `main_checkout(__file__)`, as the template does, so data paths don't follow a worktree.
3. `.gitignore`: add `*.zarr` and the template's blocks from `# Data never enters git` to the end. Their rules
   match inside every task directory, and their re-includes keep READMEs, placeholders and task evidence tracked.
   `.gitattributes`: the template's `pixi.lock` line, so a lock conflict keeps one side whole.
4. Remove any notebook-output stripping (`nbstripout` in `.gitattributes`, its install step, its CI check).
5. Copy the template's `REVIEW_GUIDE.md`, adding the repo's own rules under its last heading, and its
   `.github/pull_request_template.md`.
6. In `AGENTS.md`, one short section naming the plugin and where the working objects live; delete restated rules.
7. `uvx cruft link https://github.com/quadbio/analysis_template`, so the repo receives the template's updates.
