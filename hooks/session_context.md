This repository follows the analysis-workflow conventions. Load the `analysis-workflow` skill before writing
analysis code, outputs or data. Always:

1. One task = one session = one git worktree = one directory `analysis/<topic>/.../<name>_vN/`. A new task
   directory needs a new session, which the human starts with `claude --worktree <name>` in the main checkout.
   Analysis only moves forward: earlier task directories are never edited, fixed or updated.
2. Every output path comes from `task_paths(__file__)` (package `analysis_workflow`); never a bare relative path.
3. Ask the human which working object (and which label keys) is current, never inferring it from a script or the
   newest file name; and agree what the task delivers (a default, if set, is listed below), recorded in its README.
4. Shared objects grow by addition only (`commit_adata`), and only after sign-off on the dry run.
5. Agents never write to `data/<dataset>/results/` or the central `figures/`; those are the human lane.
6. A worktree, and every batch job submitted from it, runs on the main checkout's environment; only the human
   installs it, in the main checkout. The line below says whether it is active in every Bash command. Batch jobs
   run `pixi run --manifest-path "$MAIN/pixi.toml" --as-is ...`.
