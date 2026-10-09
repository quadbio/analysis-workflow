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
- compute and job submission: the environment's own docs or skill;
- **every scientific plot: the `sci-figures` skill**; cell-type annotation: `cell-type-annotation`;
- why the storage rules are what they are: `references/storage.md`.

## Where code goes

- Science code that several tasks need goes to a code repo, plotting code included. Figure code is copied only
  between versions of one task. The analysis repo's own package holds `FilePaths`, dataset versioning and a CLI.
- Look before writing: existing packages (scverse, then its ecosystem), sibling code repos, earlier task directories.
- A value becomes a constant in `_constants.py` when it is a stable project fact that several scripts would
  otherwise hardcode (a dataset root, a registered resource). Not task outputs, not the current working object
  (stated per session), not parameters (they stay in their script).

## Two lanes

Humans work in notebooks, flat under `analysis/<topic>/`, writing to `data/<dataset>/results/` and
`figures/<topic>/`; notebook outputs are committed. Agents work in task directories, with scripts, and never write
into the human lane.

## Tasks

**Start**
1. One task = one session = one git worktree = one branch = one directory `analysis/<topic>/.../<name>_vN/`, merged
   through one or more PRs. A new task directory needs a new session; a later answer to the same question is `_v2`.
2. Copy `assets/task_template/`.
3. Ask which working object and which label keys are current, and record them under Inputs. Never infer them from a
   script or the newest file name.
4. Rename freely until the first write-back or the merge; then the name is frozen, because keys carry it.

**Run**
- Every output path comes from `PATHS = task_paths(__file__)` in `_common.py`; `PATHS.ensure()` in the writer.
  A bare relative path written from a worktree dies with the worktree.

  | dir | tracked | lives in | holds |
  | --- | --- | --- | --- |
  | `results/` | yes | this checkout | small evidence tables; past ~1 MB they belong in `outputs/` |
  | `reports/` | yes | this checkout | the findings report |
  | `figures/` | no | main checkout | `fig1_<name>.pdf` … in reading order |
  | `outputs/` | no | main checkout | data artifacts |
  | `logs/` | no | main checkout | batch-job logs, passed as an absolute path |

- Another task's untracked outputs: `task_paths(<its _common.py>).outputs`. Read the main checkout by absolute
  path; never `cd` into it.
- A figure that prints a number may carry `scripts/verify.py` re-deriving it. A code package's invariants belong in
  that package's tests.

**Finish**
1. Report, and the README: Inputs, Outputs, Write-back, Running, Notes.
2. Write back: dry run, sign-off on that diff, then `yes=True`.
3. An object other tasks will load is promoted to `data/<dataset>/processed/` at sign-off. Ask which subdirectory;
   record the path.
4. `analysis-workflow check layout`, then push.

## Data

| `data/<dataset>/` | holds | written by |
| --- | --- | --- |
| `raw/` | bytes as they arrived | nobody, after arrival |
| `resources/` | curated inputs that are not data: gene lists, marker tables | a human, rarely |
| `processed/` | objects code loads, the working objects among them | notebooks; tasks by promotion |
| `results/` | a notebook's own outputs, prefixed with its stem | humans only |

**Working objects** are AnnData zarr stores, `<name>_<YYYY-MM-DD>.zarr`, in which results accumulate.
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
- A worktree runs on the main checkout's environment: `pixi run --manifest-path <main>/pixi.toml …`.
  `pixi install`/`add`/`lock` run only in the main checkout, by the human, one session at a time.
- Verify an environment change with import smoke tests and `--help`, not by re-running analyses.

## Review

Each repo keeps a `REVIEW_GUIDE.md` for reviewers that cannot load this plugin; its generic half is
`assets/REVIEW_GUIDE.md`.
