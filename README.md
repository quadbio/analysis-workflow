# analysis-workflow

A Claude Code plugin for computational-biology analysis repos where humans and coding agents work side by side.
Both follow the analysis template's `CONVENTIONS.md`: versioned task directories, output paths that survive a git
worktree being removed, and a shared AnnData zarr *working object* per dataset that grows by additive write-back
only. The plugin adds what only agents do: one task per session, git worktree and pull request.

| Part | What it does |
| --- | --- |
| `skills/analysis-workflow/` | The agent's side: task lifecycle in a worktree, sign-off, PRs, environments, setting up repos. Loaded on demand. |
| `hooks/` | Always-on core rules and the main checkout's environment at session start; blocks worktree-unsafe output paths, `pixi install` in a worktree, and task directories off the template. |
| `src/analysis_workflow/` | `task_paths`, `main_checkout`, `commit_adata`, `keys_on_disk`, `analyze_anndata_size`; the task template; `analysis-workflow new` and `check layout`. |

It assumes analysis repos made from [analysis_template](https://github.com/quadbio/analysis_template)
(pixi-managed) and code repos from the [scverse cookiecutter](https://github.com/scverse/cookiecutter-scverse)
(uv-managed). Nothing in it is specific to a dataset, an analysis or a compute environment.

## Use

Start each analysis task as its own session, from the analysis repo's main checkout. Pull it first: the worktree
branches from `origin`'s default branch but runs on the main checkout's environment.

```bash
claude --worktree <task>
```

1. The agent works on that worktree's branch, in a new task directory `analysis/<dataset>/<topic>/agent_<task>_vN/`;
   a later answer to the same question gets the next version, in a new session. Earlier task directories are never
   edited.
2. It asks you which working object is current and agrees what the task delivers (by default your `deliverables`
   setting), then works in scripts; outputs go to the task directory.
3. Results reach a shared working object only after you sign off the dry run.
4. It opens a PR whose body holds the details; the task README summarizes each PR. Once it is merged and its batch
   jobs have finished, leave with `/exit` and remove the worktree.

You work the same way, in `human_` task directories in the main checkout (the template's `CONVENTIONS.md`). A task that changes the environment locks, installs and tests
it in a temporary checkout beside the main one; after its merge you pull and run `pixi install` there. With no
analysis repo yet, ask Claude to start an analysis project: the skill sets one up.

## Install

**The plugin**, once per machine, from the [quadbio marketplace](https://github.com/quadbio/claude-plugins). The
skill is then available everywhere; the hooks and session-start rules act only in repos that enable the plugin in
their committed `.claude/settings.json`. Every repo made from
[analysis_template](https://github.com/quadbio/analysis_template) does, and depends on the package in its
`pixi.toml` (its lock pins the commit; `pixi update` moves it). To adopt an existing repo, ask Claude to adopt the
conventions.

**Settings**, saved with `/plugin configure analysis-workflow@quadbio`:

| Setting | Default | Meaning |
| --- | --- | --- |
| `deliverables` | `a figure` | What a task delivers unless you choose otherwise at its start; recorded in the task README. Blank: the agent asks. |

## Develop

```bash
uv sync --group dev
uv run pytest
uv run pre-commit run --all-files
claude plugin validate .
claude --plugin-dir .        # try the skill and hooks from this checkout
```

For live package edits in an analysis repo, depend on the checkout instead:
`analysis-workflow = { path = "../analysis-workflow", editable = true }`.

## Release

Bump `version` in `.claude-plugin/plugin.json` and merge: the marketplace follows `main`, and users update when the
version changes.

## License

MIT
