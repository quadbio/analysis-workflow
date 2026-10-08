"""Where an analysis task's outputs go, so that none of them dies with a git worktree."""

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: The directory under the repo root that holds notebooks and task directories.
ANALYSIS_DIR = "analysis"

#: Task subdirectories git tracks: small, reviewable, they ride the PR.
TRACKED_TASK_DIRS = ("results", "reports")

#: Task subdirectories git ignores: heavy or noisy, anchored to the main checkout.
UNTRACKED_TASK_DIRS = ("figures", "outputs", "logs")

#: Directory names that are *inside* a task rather than a task themselves.
RESERVED_TASK_SUBDIRS = frozenset(
    {*TRACKED_TASK_DIRS, *UNTRACKED_TASK_DIRS, "scripts", "slurm", "notebooks", "audits", "docs"}
)

#: Tooling that keeps its own ``logs/`` or ``results/`` and must not be read as a task.
NON_TASK_DIRS = frozenset({".pixi", ".git", ".venv", "wandb", "site-packages", "node_modules", "__pycache__"})


@lru_cache
def _main_checkout(directory: str) -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=directory,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError) as err:
        raise RuntimeError(f"{directory} is not inside a git checkout; cannot locate the main checkout") from err
    return Path(out).parent


def main_checkout(start: str | Path = ".") -> Path:
    """Absolute path of the *main* checkout of the repository containing ``start``.

    Works from any git worktree: ``--git-common-dir`` points at the main checkout's ``.git``.
    Pass ``__file__`` from a script, so the answer does not depend on where it is run from.
    """
    path = Path(start).resolve()
    while not path.is_dir():
        path = path.parent
    return _main_checkout(str(path))


@dataclass(frozen=True)
class TaskPaths:
    """The output directories of one analysis task. Nothing exists until :meth:`ensure`."""

    task: Path
    results: Path
    reports: Path
    figures: Path
    outputs: Path
    logs: Path

    def ensure(self) -> "TaskPaths":
        """Create the directories. Call this from the writer, never at import time."""
        for name in (*TRACKED_TASK_DIRS, *UNTRACKED_TASK_DIRS):
            getattr(self, name).mkdir(parents=True, exist_ok=True)
        return self


def task_paths(file: str | Path) -> TaskPaths:
    """Resolve the output directories for the task that ``file`` belongs to.

    Pass ``__file__``. The task directory is the nearest ancestor under ``analysis/`` whose name
    is not a known task subdirectory, so ``<task>/_common.py`` and ``<task>/scripts/_common.py``
    both resolve to ``<task>``.
    """
    path = Path(file).resolve()
    parts = path.parts
    if ANALYSIS_DIR not in parts:
        raise ValueError(f"{path} is not under an '{ANALYSIS_DIR}/' directory")
    checkout = Path(*parts[: parts.index(ANALYSIS_DIR)])

    task = path.parent
    while task.name in RESERVED_TASK_SUBDIRS:
        task = task.parent
    if task in (checkout / ANALYSIS_DIR, checkout):
        raise ValueError(f"{path} is not inside a task directory under '{ANALYSIS_DIR}/'")

    main_task = main_checkout(path) / ANALYSIS_DIR / task.relative_to(checkout / ANALYSIS_DIR)
    return TaskPaths(
        task=task,
        results=task / "results",
        reports=task / "reports",
        figures=main_task / "figures",
        outputs=main_task / "outputs",
        logs=main_task / "logs",
    )
