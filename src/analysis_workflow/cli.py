"""``analysis-workflow check layout``: report the layout problems the task conventions prevent."""

import subprocess
from pathlib import Path

import typer

from analysis_workflow.paths import ANALYSIS_DIR, NON_TASK_DIRS, TRACKED_TASK_DIRS, UNTRACKED_TASK_DIRS, main_checkout

app = typer.Typer(no_args_is_help=True)
check = typer.Typer(no_args_is_help=True)
app.add_typer(check, name="check", help="Report problems; never change anything.")

# Reporting thresholds, tuning knobs rather than facts about a project.
HEAVY_RESULT_BYTES = 1_000_000  # a tracked evidence table this big is a data artifact in a csv costume
HEAVY_REPORT_BYTES = 20_000_000  # reports embed base64 figures, so large is fine, but not this large


def _is_task_output(path: Path, root: Path) -> bool:
    """True when ``path`` is a task's own output dir, not one nested in tooling or in another."""
    rel = path.relative_to(root)
    if NON_TASK_DIRS & set(rel.parts):
        return False
    # a results/ inside results/, or a logs/ inside outputs/, belongs to whatever made it
    return not set(rel.parts[:-1]) & {*TRACKED_TASK_DIRS, *UNTRACKED_TASK_DIRS}


def _tracked(main: Path) -> list[str]:
    return subprocess.run(
        ["git", "-C", str(main), "ls-files", ANALYSIS_DIR], capture_output=True, text=True, check=True
    ).stdout.splitlines()


def stray_worktree_outputs(main: Path) -> list[Path]:
    """Untracked output written inside a worktree, which dies when the worktree is removed."""
    worktrees = main / ".claude" / "worktrees"
    if not worktrees.is_dir():
        return []
    stray = []
    for tree in sorted(p for p in worktrees.iterdir() if p.is_dir()):
        for name in UNTRACKED_TASK_DIRS:
            for found in (tree / ANALYSIS_DIR).rglob(name):
                if found.is_dir() and any(found.iterdir()) and _is_task_output(found, tree):
                    stray.append(found)
    return sorted(stray)


def orphaned_outputs(main: Path) -> list[Path]:
    """Output dirs in the main checkout with no tracked task beside them: abandoned or deleted tasks."""
    tracked_dirs = {str(Path(f).parent) for f in _tracked(main)}
    orphans = []
    for name in UNTRACKED_TASK_DIRS:
        for found in (main / ANALYSIS_DIR).rglob(name):
            if not found.is_dir() or not any(found.iterdir()) or not _is_task_output(found, main):
                continue
            task = str(found.parent.relative_to(main))
            if not any(d == task or d.startswith(f"{task}/") for d in tracked_dirs):
                orphans.append(found)
    return sorted(orphans)


def heavy_tracked(main: Path) -> list[tuple[Path, int, str]]:
    """Tracked files too large for the directory they are in."""
    heavy = []
    for rel in _tracked(main):
        path = main / rel
        if not path.is_file():
            continue
        parts, size = Path(rel).parts, path.stat().st_size
        if "results" in parts and size > HEAVY_RESULT_BYTES:
            heavy.append((Path(rel), size, "belongs in outputs/"))
        elif "reports" in parts and size > HEAVY_REPORT_BYTES:
            heavy.append((Path(rel), size, "outsized even for an embedded-figure report"))
    return sorted(heavy, key=lambda t: -t[1])


@check.command("layout")
def layout(start: Path = typer.Argument(Path("."), help="Any path inside the repository.")) -> None:
    """Report stray, orphaned and oversized task outputs. Never deletes anything."""
    main = main_checkout(start)
    typer.echo(f"main checkout: {main}\n")

    stray = stray_worktree_outputs(main)
    typer.echo(f"[stray worktree output]  {len(stray)} found")
    for p in stray:
        typer.echo(f"  {p.relative_to(main)}  — will be lost when the worktree is removed")

    orphans = orphaned_outputs(main)
    typer.echo(f"\n[orphaned output dirs]   {len(orphans)} found")
    for p in orphans:
        typer.echo(f"  {p.relative_to(main)}  — no tracked task beside it")

    heavy = heavy_tracked(main)
    typer.echo(f"\n[heavy tracked files]    {len(heavy)} found")
    for rel, size, why in heavy:
        typer.echo(f"  {size / 1e6:8.1f} MB  {rel}  — {why}")

    problems = len(stray) + len(orphans) + len(heavy)
    typer.echo(f"\n{problems} item(s) to look at." if problems else "\nClean.")
