---
name: analysis-workflow
description: >-
  Conventions for computational-biology analysis repos (single-cell, spatial) where humans work in Jupyter
  notebooks and coding agents work in scripts, side by side. Covers the analysis-repo/code-repo split, the human
  and agent lanes, the task lifecycle (one task = one session = one git worktree = one versioned directory),
  worktree-safe output paths (`task_paths`), the `data/` layout, shared AnnData zarr working objects and their
  additive write-back (`commit_adata`), promotion to `processed/`, environments and review. Use whenever starting,
  running or finishing an analysis task, writing any output from an analysis script, reading or writing a working
  object, adding a dataset path or constant, setting up or adopting these conventions in a repo, or reviewing an
  analysis pull request.
---

# Analysis workflow

Humans and several agents work in the same analysis repo at once, isolated by git worktrees, pull requests and
task directories. Most rules below exist to make that safe. A short always-on summary arrives at session start;
this file is the full contract.

**Neighbours: use them, don't restate them.**
- The repo's `AGENTS.md`: its datasets, where its working objects live, environment specifics, companion
  packages. Repo facts beat this skill's examples.
- Compute and job submission: the environment's own docs or skill. This skill only says where logs go.
- **Every scientific plot or figure: the `sci-figures` skill.**
- Cell-type annotation: the `cell-type-annotation` skill.
- Setting up a repo, or adopting these conventions in one: `references/repos.md`. Working-object internals:
  `references/storage.md`.

## Repos

|  | analysis repo | code repo |
| --- | --- | --- |
| made from | [analysis_template](https://github.com/quadbio/analysis_template) | [scverse cookiecutter](https://github.com/scverse/cookiecutter-scverse) |
| managed with | pixi | uv |
| holds | notebooks, task dirs, `data/` (gitignored), a small local package | reusable, tested science code |

- The analysis repo's own package holds `FilePaths` (`_constants.py`), dataset versioning and a CLI; nothing
  scientific.
- Code several tasks need goes to a code repo, installed into the analysis environment as an editable path
  dependency. That includes plotting code once more than one task needs it. Figure code is copied only between
  versions of the same task.
- Before writing anything new, look for it: an existing package (scverse core, then its ecosystem), then the
  sibling code repos and earlier task directories. Expect a near-miss; extending it beats starting over.

**When a value becomes a constant in `_constants.py`:** when it is a stable fact about the project that more than
one script, notebook or task would otherwise hardcode, such as a dataset root or a registered resource file.
Not task outputs (`task_paths`), not the current working object (stated per session, recorded in the task
README), and not parameters or thresholds (they stay in the script that uses them).

## Two lanes

|  | human lane | agent lane |
| --- | --- | --- |
| works in | notebooks, flat under `analysis/<topic>/` | a task directory `analysis/<topic>/.../<name>_vN/` |
| writes | notebook cells | scripts |
| outputs go to | `data/<dataset>/results/`, the central `figures/<topic>/` | the task's own directories (below) |

Agents never write into the human lane. Notebook outputs are committed: they are the record of what a notebook
produced.

## Task lifecycle

**Start**
1. One task = one session = one git worktree = one branch = one directory, merged through one or more PRs. A new
   task directory needs a fresh session: finish and hand over rather than opening a second one mid-session.
2. Copy `assets/task_template/` (in this skill) to `analysis/<topic>/.../<name>_v1/`. A later answer to the same
   question is `<name>_v2`, a new task.
3. Ask the human which working object is current and which label keys (e.g. annotation level) to use. Never
   infer either from an existing script or the newest file name; those go stale. Record both under Inputs.
4. The name may change while the task is in flight. Rename before any write-back, because the keys carry it.
   Once merged, it is frozen.

**Run**
- Work in scripts. Every output path comes from `PATHS = task_paths(__file__)` in the task's `_common.py`; call
  `PATHS.ensure()` in the writer, never at import. A bare relative path written from a worktree dies with the
  worktree, and nothing warns.
- Outputs split by durability, not by kind:

  | dir | tracked | lives in | holds |
  | --- | --- | --- | --- |
  | `results/` | yes | this checkout, rides the PR | small evidence tables (csv, json); past ~1 MB it belongs in `outputs/` |
  | `reports/` | yes | this checkout | the findings report (md, or html with embedded figures) |
  | `figures/` | no | the main checkout | `fig1_<name>.pdf` … `figN_<name>.pdf`, numbered in reading order |
  | `outputs/` | no | the main checkout | data artifacts |
  | `logs/` | no | the main checkout | batch-job logs |

- Another task's untracked outputs live in the main checkout: `task_paths(<its _common.py>).outputs`, or
  `main_checkout(__file__)` for anything else there. Read them by absolute path; never `cd` into the main checkout.
- Batch jobs write their logs into `PATHS.logs`, passed as an absolute path and created before submission.
- A figure that prints a number may carry a `scripts/verify.py` re-deriving those claims from the record the
  figure was drawn from. Claims only: an invariant of a code package belongs in that package's tests.

**Finish**
1. Write the report and fill the README: Inputs (real files), Outputs, Write-back, how to run, and Notes (the
   decisions a reader would otherwise reverse-engineer).
2. Write back (below): dry run, show the diff, get sign-off, then write.
3. Promote an object other tasks will load to `data/<dataset>/processed/`, decided at sign-off. Which
   subdirectory is not guessable: ask. Record the final path in the README.
4. Run `analysis-workflow check layout`; it reports stray, orphaned and oversized outputs, and pruning is yours.
5. Push before the session ends.

## Data

`data/` is gitignored, and its paths come from `FilePaths`, never from literals.

| `data/<dataset>/` | holds | written by |
| --- | --- | --- |
| `raw/` | bytes as they arrived: instrument output, downloaded atlases | nobody, after arrival |
| `resources/` | curated inputs that are not data: gene lists, marker tables, panel descriptions | a human, rarely |
| `processed/` | objects code loads to do new work, the working objects among them | notebooks; tasks by promotion |
| `results/` | a notebook's own outputs, file names prefixed with the notebook's stem | humans only |

**Working objects.** Each dataset has AnnData **zarr** stores, `<name>_<YYYY-MM-DD>.zarr`, in which analysis
results accumulate; the repo's `AGENTS.md` says where. Which one is current is stated per session, never inferred.
- Read only what you need: `ad.io.read_elem(zarr.open_group(path)["obs"])` beats `ad.read_zarr` by orders of
  magnitude; `ad.experimental.read_lazy` gives a lazy whole object.
- Write back with `commit_adata(adata, path)`, a dry run, then `commit_adata(adata, path, yes=True)` after
  sign-off on that diff. It writes only keys not yet on disk, so an object built from one slot works too.
- **Additions only.** Never write an in-memory object back over a working object: by the time an analysis
  finishes its copy is stale, and writing it would erase what other sessions added. Changing or removing a key
  means a new dated copy; keep the old one so old scripts still run.
- Recomputing an existing key and committing is a silent no-op. Use a new key.
- Every written key carries the task's version suffix (`obs["niche_v3"]`) and is listed in the task README, so
  grepping the READMEs for a key finds the task that made it.
- Labels: one categorical `obs` column with names as categories and colours in `uns["<key>_colors"]`. Copy the
  conventions the existing annotations already use.
- Size test: if a result would grow the object materially (`analyze_anndata_size`), it becomes a standalone
  minimal AnnData with its own `obs_names`, never a bare `.npy`, which loses them.
- Everything else (figures, tables, a task's own objects) is written plainly, without temp files or renames: a
  committed script rebuilds it.

## Environments

- The root `pixi.toml` is the shared environment. Reusability decides what goes in: a package likely to be
  carried forward is worth making work there; five candidates for a benchmark belong in a task-local
  `pixi.toml`, promoted later if one earns it.
- The root manifest installs the repo's own package editable (`path = "."`), from the main checkout. So:
  - a worktree runs on the main checkout's environment:
    `pixi run --manifest-path <main checkout>/pixi.toml python script.py`. A plain `pixi run` there would build a
    second environment inside the worktree;
  - `pixi install`, `add` and `lock` run only in the main checkout, one session at a time; from a worktree, hand
    the command to the human;
  - a worktree's own `src/` edits are invisible to that environment.
- Verify an environment change with import smoke tests and `--help`, not by re-running analyses.

## Review

Each repo keeps a `REVIEW_GUIDE.md` for reviewers that cannot load this plugin. Its generic half comes from the
template (source: `assets/REVIEW_GUIDE.md` here), and repo specifics go below it.
