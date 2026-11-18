---
name: trace-lineage
description: >-
  Explain how a data artifact was made: trace a key in a shared AnnData or SpatialData store, or a file in a task's
  outputs, back through the tasks that produced it, and write a report with the graph and a summary of its history.
  Use when asked what created an artifact, what it is based on, for its lineage or provenance, or which tasks a
  published artifact rests on.
---

# Trace an artifact's lineage

One artifact per report: a key in a store, or a file.

1. From the analysis repo, run

   ```bash
   analysis-workflow trace <store> <key> --format json    # or: analysis-workflow trace <file> --format json
   ```

   If it names tasks without declared inputs, say which, offer to run the `declare-inputs` skill on them, and
   stop: a trace is only as complete as the declarations it follows.
2. `--format mermaid` gives the graph: artifacts as nodes, each edge labelled with the task that made its target.
   `--format tasks` lists the task directories on the path.
3. Read the README of each task on the path for its author, its date and its opening sentence.
4. Write the report: the graph in a `mermaid` block, then the summary, in exactly this form.

   ```markdown
   ## <key> in <store>

   Written by <task> (<author>, <date>): <clause from the task README's opening sentence>.

   History, oldest first
   1. <task> (<author>, <date>): from <inputs used>, giving <keys or files written>.
   2. ...

   Source data: <files under raw/ and resources/, or outside the repo>
   No record: <artifacts on the path that no record covers, or "none">
   ```

5. Print the report, and save it where the human says if they name a path.

The summary states what the trace and the READMEs say, nothing more. An artifact marked `no record`, or a task
that is not in this checkout, is listed as that.
