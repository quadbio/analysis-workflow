---
name: analysis-workflow
description: >-
  Conventions for analysis repos where humans (notebooks) and coding agents (scripts) work side by side. Use when
  starting, running or finishing an analysis task; writing any output from an analysis script; reading or writing a
  shared AnnData working object; adding a dataset path or constant; starting a new analysis project or adopting
  these conventions in an existing repo; or reviewing an analysis pull request.
---

# Analysis workflow

Humans and several agents share one analysis repo, isolated by git worktrees, pull requests and task directories.
These rules keep that safe.

**First, check for the repo.** Outside a repo whose `.claude/settings.json` enables this plugin, set one up with the
human before anything else: create the analysis repo and, if wanted, its code repo, or adopt an existing repo.
Steps: `references/repos.md`.

Elsewhere:
- the repo's `AGENTS.md`: its datasets, where its working objects live, its environments. It wins over examples here;
- figures, analysis methods, and the compute environment with its job submission: their own docs or skills.
  Nothing here covers them, and these conventions hold on any machine;
- why the storage rules are what they are: `references/storage.md`.

## Where code goes

- Science code that several tasks need goes to a code repo; a new version of a task copies what it reuses from the
  one it follows. The analysis repo's own package holds `FilePaths`, dataset versioning and a CLI.
- A task that changes a code repo does so in a worktree of that repo, added from the same session:
  `git -C <code repo> worktree add .claude/worktrees/<task> -b <branch>`.
- Look before writing: existing packages (scverse, then its ecosystem), sibling code repos, earlier task directories.
- A value becomes a constant in `_constants.py` when it is a stable project fact that several scripts would
  otherwise hardcode (a dataset root, a registered resource). Not task outputs, not the current working object
  (stated per session), not parameters (they stay in their script).

## Two lanes

`analysis/` is split by dataset, then by broad topic: `analysis/<dataset>/<topic>/`, with the dataset level even when
there is one dataset. Topics, such as `preprocessing/`, `annotation/` or `spatial/`, can mostly be worked on in any
order. Humans work in notebooks, flat under a topic, writing to `data/<dataset>/results/` and
`figures/<dataset>/<topic>/`; notebook outputs are committed. Agents work in task directories under a topic, with
scripts.

## Tasks

**Start**
1. A task is one branch, merged through one or more PRs; a later answer to the same question is the next version,
   in a new session. Only task directories end in `_vN`; a topic never does.
2. Copy `assets/task_template/` into the task directory.
3. Settle what session rule 3 asks, the working object with its label keys and the deliverables, and record both in
   the README. Deliverables are any of a report, a figure, an HTML page, just results in `outputs/` and a
   write-back; start from the default the session start lists, if any, which the human may change for this task.
4. Rename freely until the first write-back or the merge; then the name is frozen, because keys carry it.

**Run**
- `PATHS = task_paths(__file__)` lives in `scripts/_common.py`; call `PATHS.ensure()` in the writer.

  | dir | tracked | lives in | holds |
  | --- | --- | --- | --- |
  | `results/` | yes | this checkout | small evidence tables; past ~1 MB they belong in `outputs/` |
  | `reports/` | yes | this checkout | a report, if one is a deliverable |
  | `figures/` | no | main checkout | figures |
  | `outputs/` | no | main checkout | data artifacts |
  | `logs/` | no | main checkout | batch-job logs, passed as an absolute path |

- Another task's untracked outputs: `task_paths(<its _common.py>).outputs`. Read the main checkout by absolute
  path; never `cd` into it.
- Scripts go in `scripts/`: the steps as `NN_<step>.py`, numbered in run order, and batch-job scripts beside the
  code they run. A batch job gets the main checkout as `$MAIN` from the submit command, never hardcoded, and logs to
  `PATHS.logs`; how to submit it is the compute environment's concern.
- A deliverable that states a number may carry `scripts/verify.py` re-deriving it. A code package's invariants
  belong in that package's tests.

**Record.** The task README, in the task template's layout, is the overview, kept current. The deliverables hold the
findings; the README links to them rather than restating them. The details of each PR go in its body, laid out by
the repo's `.github/pull_request_template.md`; the README gives each PR, and each issue the session opened in any
repo, a short summary.

**Finish**
1. The agreed deliverables, and the README brought up to date, its jobs counted with the compute environment's
   tools.
2. Write back: dry run, sign-off on that diff, then `yes=True`.
3. An object other tasks will load is promoted to `data/<dataset>/processed/` at sign-off: a working object into
   `working/`, anything else into a subdirectory named for what it holds. Confirm the path, then record it.
4. `analysis-workflow check layout`, then push.
5. Open the PR, its body from the PR template; then add it with a short summary to the README and push again. The
   body is edited until the merge, never after.
6. The worktree is removed only once no batch job submitted from it is still queued or running.

## Data

| `data/<dataset>/` | holds | written by |
| --- | --- | --- |
| `raw/` | bytes as they arrived | nobody, after arrival |
| `resources/` | curated inputs that are not data: gene lists, marker tables | a human, rarely |
| `processed/` | objects code loads: working objects in `working/`, others in subdirectories named for their content | notebooks; tasks by promotion |
| `results/` | a notebook's own outputs, prefixed with its stem | humans only |

**Working objects** are AnnData zarr stores, `processed/working/<name>_<YYYY-MM-DD>.zarr`, in which results
accumulate.
- Read only what you need: `ad.io.read_elem(zarr.open_group(path)["obs"])`, or `ad.experimental.read_lazy`.
- Write back only through `commit_adata`: additions only. Never write an in-memory object over a working object.
  Changing or removing a key means a new dated copy; recomputing an existing key is a silent no-op.
- Keys carry the task's version suffix (`obs["niche_v3"]`) and are listed in its README.
- Labels: one categorical `obs` column, colours in `uns["<key>_colors"]`, as the existing annotations do.
- A result that would grow the object materially (`analyze_anndata_size`) becomes a standalone AnnData on the same
  `obs_names`, never a bare `.npy`.
- Everything else is written plainly.

## Environments

- The root `pixi.toml` is shared; reusability decides what goes in. A benchmark's candidates go task-local.
- The human installs the main checkout's environment one session at a time. The session-start hook activates it
  for every Bash command, subagents' included: run `python …` directly. Anything run outside a session uses
  `pixi run --manifest-path <main>/pixi.toml --as-is …`, as batch jobs do; without `--as-is`, pixi relocks or
  installs into main whenever its manifest or lock is ahead of the environment.
- A task that changes `pixi.toml` locks, installs and tests it in a temporary checkout beside the main one, where
  the relative path dependencies resolve; main's environment stays untouched. Commit `pixi.toml`, then
  `git worktree add --detach <main>-lock HEAD` (`<main>` is the main checkout's path), and pass
  `--manifest-path <main>-lock/pixi.toml` to `pixi lock`, `pixi install --frozen` and the checks'
  `pixi run --as-is`. Then, in this order: copy its `pixi.lock` into the task's worktree, check
  `git diff --stat pixi.lock`, commit, and `git worktree remove --force` the temporary checkout. The repo's settings
  list `../<main checkout's directory>-lock` under `permissions.additionalDirectories`, so the copy needs no
  approval. After the merge the human pulls and runs `pixi install` in the main checkout.
- The hook puts the worktree's `src/` first on `PYTHONPATH`, so the repo's own package is imported from the
  worktree. An editable code repo still imports from its main checkout; to run a code-repo worktree's edits, prepend
  its `src/` too. Paths to shared data come from `main_checkout(__file__)`, never from `__file__` alone, which
  follows the worktree.
- A Jupyter kernel, or a direct call to an environment's `python`, skips pixi's activation: variables the
  environment sets (such as `CONDA_PREFIX`) are missing unless the kernelspec passes them.
- Verify an environment change with import smoke tests and `--help`, not by re-running analyses.

## Review

A repo's PR template and the generic half of its `REVIEW_GUIDE.md`, for reviewers that cannot load this plugin,
come from [the analysis template](https://github.com/quadbio/analysis_template/tree/main/%7B%7Bcookiecutter.project_name%7D%7D).
