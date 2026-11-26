"""``analysis-workflow new``: start a task; ``check ...``: report problems; ``trace``: how an artifact was made."""

import datetime
import re
import secrets
import shutil
import subprocess
from pathlib import Path

import typer

from analysis_workflow.graph import dot, render
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
    empty_dirs,
    main_checkout,
)
from analysis_workflow.provenance import records, uncovered
from analysis_workflow.trace import changed_since_declared, declared, missing_inputs, task_dirs, trace

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


def new_task(
    path: Path,
    author: str | None = None,
    notebook: str | None = None,
    today: datetime.date | None = None,
    ported_from: str | None = None,
) -> Path:
    """Create the task directory ``path`` from the task template; return it.

    ``path`` is ``analysis/<dataset>/<topic>/.../<lane>_<name>_vN``, relative to the working directory or absolute,
    and ``vN`` must be the next version of ``<name>`` beside it, counted over both lanes, in this checkout and the
    main one. ``author`` defaults, for a human's task, to the git user name; an agent's task names its model.
    ``notebook`` (``NN_<step>``) copies the repo's starter notebook into ``notebooks/``. ``ported_from`` names the
    older work the task ports, as ``<repo>:<path>@<commit>``, in the README's header; such a task keeps that
    work's version, which must be above every version beside it.
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
    if author is None and m["lane"] == "human":
        author = subprocess.run(
            ["git", "-C", str(checkout), "config", "user.name"], capture_output=True, text=True
        ).stdout.strip()
    if not author:
        raise ValueError("Pass --author: the model for an agent's task, or a name where git has no `user.name`.")
    parent = path.parent.relative_to(checkout)
    found = [
        v
        for d in {checkout / parent, main / parent}
        if d.is_dir()
        for c in d.iterdir()
        if (v := _version(c.name, m["name"]))
    ]
    expected = max(found, default=0) + 1
    if ported_from is not None and int(m["version"]) < expected:
        raise ValueError(f"A port keeps its version, which must be v{expected} or above in {parent}.")
    if ported_from is None and int(m["version"]) != expected:
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
        "**Id:**": f"**Id:** {secrets.token_hex(4)}",
    }
    lines = readme.read_text().splitlines(keepends=True)
    for start, line in fill.items():
        i = next(i for i, old in enumerate(lines) if old.startswith(start))
        lines[i] = line + "\n"
    if ported_from is not None:
        lines.insert(lines.index(fill["**Id:**"] + "\n") + 1, f"**Ported from:** {ported_from}\n")
    readme.write_text("".join(lines))
    return path


@app.command("new")
def new(
    path: Path = typer.Argument(..., help="analysis/<dataset>/<topic>/<human|agent>_<name>_v<N>"),
    author: str | None = typer.Option(
        None, help="A human's name or initials (default: the git user name), or the model, e.g. 'Claude Opus 5.5'."
    ),
    notebook: str | None = typer.Option(None, help="Also copy the repo's starter notebook in, as NN_<step>."),
    ported_from: str | None = typer.Option(
        None, help="The older work this task ports, as <repo>:<path>@<commit>; the task keeps its version."
    ),
) -> None:
    """Start a task directory from the task template."""
    try:
        task = new_task(path, author, notebook, ported_from=ported_from)
    except (ValueError, FileExistsError, FileNotFoundError) as err:
        typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(1) from err
    typer.echo(f"created {task}")
    for p in sorted(task.rglob("*")):
        typer.echo(f"  {p.relative_to(task)}{'/' if p.is_dir() else ''}")


@app.command("tidy")
def tidy(task: Path = typer.Argument(..., help="The task directory, at its end.")) -> None:
    """Remove the directories the task left empty."""
    try:
        found = empty_dirs(task)
    except (ValueError, RuntimeError) as err:
        typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(1) from err
    for path in found:
        shutil.rmtree(path)
        typer.echo(f"removed {path}")
    if not found:
        typer.echo("No empty directories.")


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


@check.command("provenance")
def provenance(store: Path = typer.Argument(..., help="An AnnData or SpatialData zarr store.")) -> None:
    """Report the keys of a store that no record credits to a task: written outside a `writes` block."""
    found = records(store)
    typer.echo(f"{store}: {len(found)} record(s) from {len({r['task'] for r in found})} task(s)\n")
    missing = uncovered(store)
    typer.echo(f"[keys without a record]  {len(missing)} found")
    for key in missing:
        typer.echo(f"  {key}")
    typer.echo(f"\n{len(missing)} item(s) to look at." if missing else "\nClean.")


@check.command("inputs")
def inputs(
    tasks: list[Path] = typer.Argument(None, help="Task directories; by default every task of this checkout."),
) -> None:
    """Report tasks that have no `inputs.yaml`, or whose list names something that is not there or is out of date."""
    found = [t.resolve() for t in tasks] if tasks else task_dirs(_checkouts_of(Path.cwd())[0])
    undeclared = [t for t in found if declared(t) is None]
    missing = [(t, what) for t in found for what in missing_inputs(t)]
    stale = [t for t in found if declared(t) is not None and changed_since_declared(t)]

    typer.echo(f"[inputs not declared]          {len(undeclared)} found")
    for task in undeclared:
        typer.echo(f"  {task}")
    typer.echo(f"\n[declared, but not there]      {len(missing)} found")
    for task, what in missing:
        typer.echo(f"  {task.name}: {what}")
    typer.echo(f"\n[code changed since declared]  {len(stale)} found")
    for task in stale:
        typer.echo(f"  {task}")

    problems = len(undeclared) + len(missing) + len(stale)
    typer.echo(f"\n{problems} item(s) for the `declare-inputs` skill." if problems else "\nClean.")


@app.command("trace")
def trace_command(
    artifact: Path = typer.Argument(..., help="A store in shared storage, or a file such as one in a task's outputs/."),
    key: str | None = typer.Argument(None, help="The key in the store: obs/leiden, X, tables/table/obs/leiden."),
    form: str = typer.Option(
        "tree", "--format", help="tree, json or tasks; dot or pdf for a graph of the tasks, drawn by Graphviz."
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Where `--format pdf` writes the graph; a .svg or .png suffix gives that type."
    ),
) -> None:
    """Trace one artifact back through the tasks that made it."""
    try:
        found = trace(artifact, key, start=Path.cwd())
    except ValueError as err:
        typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(1) from err
    if found.undeclared:
        typer.echo("No declared inputs for these tasks on the path; run the `declare-inputs` skill on them:", err=True)
        for task in found.undeclared:
            typer.echo(f"  {task}", err=True)
        raise typer.Exit(1)
    formats = {
        "tree": found.as_tree,
        "json": found.as_json,
        "tasks": lambda: "\n".join(found.tasks()),
        "dot": lambda: dot(found, Path.cwd()),
    }
    if form not in (*formats, "pdf"):
        typer.echo(f"Error: --format is one of {', '.join(formats)}, pdf.", err=True)
        raise typer.Exit(1)
    try:
        if form != "pdf":
            typer.echo(formats[form]())
        elif output is None:
            raise ValueError("`--format pdf` needs `--output <file>`.")
        else:
            typer.echo(f"wrote {render(dot(found, Path.cwd()), output)}")
    except (ValueError, RuntimeError) as err:
        typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(1) from err
