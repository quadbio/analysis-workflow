This repository follows the analysis-workflow conventions. Load the `analysis-workflow` skill before writing
analysis code, outputs or data. Always:

1. One task = one session = one git worktree = one directory `analysis/<topic>/.../<name>_vN/`. A new task
   directory needs a new session.
2. Every output path comes from `task_paths(__file__)` (package `analysis_workflow`); never a bare relative path.
3. Ask the human which working object (and which label keys) is current; never infer it from a script or the
   newest file name.
4. Shared objects grow by addition only (`commit_adata`), and only after sign-off on the dry run.
5. Agents never write to `data/<dataset>/results/` or the central `figures/`; those are the human lane.
6. A worktree runs on the main checkout's environment (`pixi run --manifest-path <main>/pixi.toml ...`);
   environment changes happen in the main checkout.
