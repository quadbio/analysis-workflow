---
name: declare-inputs
description: >-
  Write down what an analysis task consumed: read its scripts and notebooks and list, in the task's `inputs.yaml`,
  the stores with the keys it used, other tasks' files and data files. Use when a task is finished, before its PR;
  when `analysis-workflow trace` or `check inputs` names tasks without declared inputs; or when asked to declare,
  update or backfill inputs for one or several task directories.
---

# Declare a task's inputs

A task's code is the record of what it consumed. This skill reads it and writes the list to `<task>/inputs.yaml`,
which `analysis-workflow trace` follows from an artifact back to its sources. It works on any task directory,
a human's or an agent's, finished long ago or just now. `inputs.yaml` is the one file it adds or changes; nothing
else in an earlier task directory is touched.

## For each task directory

Given several, hand each to its own subagent, with this section as its brief.

1. Read every script and notebook of the task, `scripts/_common.py` included. Follow calls into the repo's own
   package and into sibling packages far enough to see which keys a called function uses, its defaults included.
2. List what the code consumes:
   - keys of a shared store it **uses**, not merely loads: a notebook that reads a whole object and plots two
     columns used those two. `*` stands for the whole object, as when the task copies it;
   - files of other tasks: in their `outputs/` or `results/`, and code imported from them;
   - data files: under `data/`, or outside the repo by absolute path (`~/...` for a per-user cache, such as a
     downloaded model).

   Leave out what the task writes itself, and keys it wrote and then reads back.
3. Resolve a path the code builds at run time (a date, a section name, a glob) against what is on disk.
4. Write the list below the task's id, which stays as it is. Paths inside the repo are relative to its root; keys
   are named as the store's records name them. A task that consumes nothing gets `inputs: []`.

   ```yaml
   task: "7f3a9c2e"
   inputs:
     - path: data/<dataset>/processed/working/<object>.zarr
       keys: [obs/annot_l2, obsm/X_pca, X]
     - path: data/<dataset>/processed/spatialdata/<section>.zarr
       keys: [shapes/cells, tables/table/obs/sample]
     - path: analysis/<dataset>/<topic>/<other_task>/outputs/<file>
     - path: data/<dataset>/raw/<file>
   ```

5. `analysis-workflow check inputs <task directory>`, and correct what it reports.

Report each case you were unsure of in one line: what it is, and why it may or may not count as used.
