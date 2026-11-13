"""``analysis-workflow new``: start a task directory; ``analysis-workflow check layout``: report layout problems."""

import datetime
import re
import shutil
import subprocess
from pathlib import Path

import typer

from analysis_workflow.paths import (
    ANALYSIS_DIR,
    LANES,
    NON_TASK_DIRS,
    NOTEBOOK_DIR,
    NOTEBOOK_TEMPLATE,
    TASK_TEMPLATE,
    TRACKED_TASK_DIRS,
    UNTRACKED_TASK_DIRS,
    _checkouts_of,
    main_checkout,
)

app = typer.Typer(no_args_is_help=True)
check = typer.Typer(no_args_is_help=True)
app.add_typer(check, name="check", help="Report problems; never change anything.")

TASK_NAME = re.compile(rf"(?P<lane>{'|'.join(LANES)})_(?P<name>.+)_v(?P<version>[1-9]\d*)")
NOTEBOOK_NAME = re.compile(r"\d{2}_\w+")


def _version(directory: str, name: str) -> int | None:
    """The version of ``directory`` if it answers the question ``name``, in either lane or the older unprefixed form."""
    for prefix in (*(f"{lane}_" for lane in LANES), ""):
        if m := re.fullmatch(rf"{re.escape(prefix + name)}_v(\d+)", directory):
            return int(m[1])
    return None


def new_task(path: Path, author: str, notebook: str | None = None, today: datetime.date | None = None) -> Path:
    """Create the task directory ``path`` from the task template; return it.

    ``path`` is ``analysis/<dataset>/<topic>/.../<lane>_<name>_vN``, relative to the working directory or absolute,
    and ``vN`` must be the next version of ``<name>`` beside it, counted over both lanes, in this checkout and the
    main one. ``notebook`` (``NN_<step>``) copies the repo's starter notebook into ``notebooks/``.
    """
    path = Path(path).resolve()
    checkout, main = _checkouts_of(path)
    analysis = checkout / ANALYSIS_DIR
    form = f"{ANALYSIS_DIR}/<dataset>/<topic>/<{'|'.join(LANES)}>_<name>_v<N>"
    if not path.is_relative_to(analysis) or len(path.relative_to(analysis).parts) < 3:
        raise ValueError(f"{path} is not of the form {form}, under {checkout}.")
    if not (m := TASK_NAME.fullmatch(path.name)):
        raise ValueError(f"{path.name!r} is not a task name: {form}.")
    if path.exists():
        raise FileExistsError(f"{path} already exists.")
    parent = path.parent.relative_to(checkout)
    found = [
        v
        for d in {checkout / parent, main / parent}
        if d.is_dir()
        for c in d.iterdir()
        if (v := _version(c.name, m["name"]))
    ]
    if int(m["version"]) != (expected := max(found, default=0) + 1):
        raise ValueError(f"The next version of {m['name']!r} in {parent} is v{expected}, not v{m['version']}.")
    if notebook is not None:
        if not NOTEBOOK_NAME.fullmatch(notebook):
            raise ValueError(f"{notebook!r} is not a notebook name: NN_<step>, e.g. 01_qc.")
        if not (starter := checkout / NOTEBOOK_TEMPLATE).is_file():
            raise FileNotFoundError(f"This repo has no starter notebook at {NOTEBOOK_TEMPLATE}.")

    shutil.copytree(TASK_TEMPLATE, path, ignore=shutil.ignore_patterns("__pycache__"))
    (path / NOTEBOOK_DIR).mkdir()
    if notebook is not None:
        shutil.copyfile(starter, path / NOTEBOOK_DIR / f"{notebook}.ipynb")
    readme = path / "README.md"
    fill = {
        "# ": f"# {path.name}",
        "**Date:**": f"**Date:** {today or datetime.date.today()}",
        "**Author:**": f"**Author:** {author}",
    }
    lines = readme.read_text().splitlines(keepends=True)
    for start, line in fill.items():
        i = next(i for i, old in enumerate(lines) if old.startswith(start))
        lines[i] = line + "\n"
    readme.write_text("".join(lines))
    return path


@app.command("new")
def new(
    path: Path = typer.Argument(..., help="analysis/<dataset>/<topic>/<human|agent>_<name>_v<N>"),
    author: str = typer.Option(..., help="A human's initials, or the model, e.g. 'Claude Opus 5.5'."),
    notebook: str | None = typer.Option(None, help="Also copy the repo's starter notebook in, as NN_<step>."),
) -> None:
    """Start a task directory from the task template."""
    try:
        task = new_task(path, author, notebook)
    except (ValueError, FileExistsError, FileNotFoundError) as err:
        typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(1) from err
    typer.echo(f"created {task}")
    for p in sorted(task.rglob("*")):
        typer.echo(f"  {p.relative_to(task)}{'/' if p.is_dir() else ''}")


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
