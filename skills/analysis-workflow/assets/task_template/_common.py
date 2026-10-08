"""Paths of this task. Every output path comes from here; create directories with ``PATHS.ensure()``."""

from analysis_workflow import task_paths

PATHS = task_paths(__file__)

RESULTS = PATHS.results
REPORTS = PATHS.reports
FIGURES = PATHS.figures
OUTPUTS = PATHS.outputs
LOGS = PATHS.logs

#: The working object this task reads, supplied by the human at session start and recorded in README.md.
WORKING_OBJECT = None
