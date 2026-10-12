# analysis-workflow

A Claude Code plugin for computational-biology analysis repos where humans work in Jupyter notebooks and
coding agents work in scripts, side by side. It encodes one way of keeping that safe: one task per agent
session, git worktree and versioned directory; output paths that survive the worktree being removed; and a
shared AnnData zarr *working object* per dataset that grows by additive write-back only.

| Part | What it does |
| --- | --- |
| `skills/analysis-workflow/` | The conventions: repo model, human and agent lanes, task lifecycle, `data/` layout, working objects, environments. Loaded on demand. |
| `hooks/` | Always-on core rules at session start; blocks worktree-unsafe output paths and `pixi install` in a worktree. |
| `src/analysis_workflow/` | `task_paths`, `main_checkout`, `commit_adata`, `keys_on_disk`, `analyze_anndata_size`, and `analysis-workflow check layout`. |

It assumes analysis repos made from [analysis_template](https://github.com/quadbio/analysis_template)
(pixi-managed) and code repos from the [scverse cookiecutter](https://github.com/scverse/cookiecutter-scverse)
(uv-managed). Nothing in it is specific to a dataset, an analysis or a compute environment.

## Use

Start each analysis task as its own session, from the analysis repo's main checkout:

```bash
claude --worktree <task>
```

1. The agent works on that worktree's branch, in a new task directory `analysis/<topic>/<task>_vN/`; a later
   answer to the same question gets the next version, in a new session.
2. It asks you which working object is current, then works in scripts; outputs go to the task directory.
3. Results reach a shared working object only after you sign off the dry run.
4. It opens a PR. Once it is merged, leave with `/exit` and remove the worktree.

Notebooks and environment changes (`pixi install`, `pixi add`) stay with you, in the main checkout. With no
analysis repo yet, ask Claude to start an analysis project: the skill sets one up.

## Install

**The plugin**, once per machine, from the [quadbio marketplace](https://github.com/quadbio/claude-plugins). The
skill is then available everywhere; the hooks and session-start rules act only in repos that enable the plugin in
their committed `.claude/settings.json`, as [analysis_template](https://github.com/quadbio/analysis_template) does:

```json
{
  "extraKnownMarketplaces": {
    "quadbio": { "source": { "source": "github", "repo": "quadbio/claude-plugins" } }
  },
  "enabledPlugins": { "analysis-workflow@quadbio": true }
}
```

**The package**, in the analysis repo's `pixi.toml`:

```toml
[pypi-dependencies]
analysis-workflow = { git = "https://github.com/quadbio/analysis-workflow", tag = "v0.2.0" }
```

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

Bump `version` in both `pyproject.toml` and `.claude-plugin/plugin.json` (a test checks they agree), tag
`vX.Y.Z`, then bump the `ref` in [quadbio/claude-plugins](https://github.com/quadbio/claude-plugins).

## License

MIT
