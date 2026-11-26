---
name: declare-inputs
description: >-
  Write down what an analysis task consumed: read its scripts and notebooks and list, in the task's `inputs.yaml`,
  the stores with the keys it used, other tasks' files and data files. Use when a task is finished, before its PR;
  when `analysis-workflow trace` or `check inputs` names tasks without declared inputs; or when asked to declare
  or update the inputs of one or several task directories.
---

# Declare a task's inputs

A task's code is the record of what it consumed. This skill reads it and writes the list to `<task>/inputs.yaml`,
which `analysis-workflow trace` follows from an artifact back to its sources. It works on a human's task
directory as on an agent's, finished earlier or just now. `inputs.yaml` is the one file it adds or changes; nothing
else in an earlier task directory is touched.

## For each task directory

Given several, hand each to its own subagent, with this section as its brief.

1. Read every script and notebook of the task, `scripts/_common.py` and the workflow files in `workflow/` included.
   Follow calls into the repo's own package and into sibling packages far enough to see which keys a called
   function uses, its defaults included.
2. List what the code **uses**, not merely loads: a key or a file read into a variable that nothing refers to is
   left out.
   - keys of a shared store: a notebook that reads a whole object and plots two columns used those two. A task
     that copies a store declares `*`, the whole object, also when the copy drops keys;
   - files of other tasks: in their `outputs/` or `results/`, and code imported from them;
   - data files: under `data/`, or outside the repo by absolute path (`~/...` for a per-user cache, such as a
     downloaded model).

   Leave out what the task writes itself, and keys it wrote and then reads back.
3. Resolve a path the code builds at run time (a date, a section name, a glob) against what is on disk. Files
   read from one directory by a loop or a glob are listed once, as that directory.
4. Write the list, and nothing else, to `<task>/inputs.yaml`. Paths inside the repo are relative to its root; keys
   are named as the store's records name them. A task that consumes nothing gets `[]`.

   ```yaml
   - path: data/<dataset>/processed/working/<object>.zarr
     keys: [obs/annot_l2, obsm/X_pca, X]
   - path: data/<dataset>/processed/spatialdata/<section>.zarr
     keys: [shapes/cells, tables/table/obs/sample]
   - path: analysis/<dataset>/<topic>/<other_task>/outputs/<file>
   - path: data/<dataset>/raw/<file>
   ```

5. `analysis-workflow check inputs <task directory>`, and correct what it reports.

Report each case you were unsure of in one line: what it is, and why it may or may not count as used.
