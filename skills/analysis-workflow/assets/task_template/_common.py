"""Shared paths for this task. Copied with the template; edit in place.

Every output path in the task comes from here, so nothing is a bare relative path: a relative write
from a git worktree lands in the worktree and disappears when it is removed.

    results/  reports/          tracked -> stay in this checkout, ride the pull request
    figures/  outputs/  logs/   ignored -> anchored to the MAIN checkout, survive the worktree

Nothing is created at import time. Call ``PATHS.ensure()`` in the writer, so a dry run stays dry.
"""

from analysis_workflow import task_paths

PATHS = task_paths(__file__)

#: Small, reviewable evidence tables and the task's report.
RESULTS = PATHS.results
REPORTS = PATHS.reports

#: Heavy or noisy: figures, data artifacts, batch-job logs.
FIGURES = PATHS.figures
OUTPUTS = PATHS.outputs
LOGS = PATHS.logs

#: The working object this task reads: an AnnData zarr store, supplied by the human at session
#: start and recorded in README.md. Never inferred: which object is current changes.
WORKING_OBJECT = None
