"""Task paths, additive AnnData write-back and layout checks for analysis repos."""

from importlib.metadata import version

from analysis_workflow.paths import TaskPaths, main_checkout, task_paths
from analysis_workflow.size import analyze_anndata_size
from analysis_workflow.working import commit_adata, keys_on_disk

__all__ = ["TaskPaths", "analyze_anndata_size", "commit_adata", "keys_on_disk", "main_checkout", "task_paths"]
__version__ = version("analysis-workflow")
