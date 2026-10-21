#!/usr/bin/env python3
"""Keep every task directory in the template's layout.

A task directory (`analysis/<dataset>/<topic>/.../<name>_vN/`) holds at its top only what the task template holds
(`skills/analysis-workflow/assets/task_template/`), the output directories of `task_paths` and a task-local
environment. Its README's title is the directory's name, and its other headings are the template README's, all of
them and in order. Both are read from their sources, the template and `paths.py`, so a change there is a change here.

PreToolUse (Edit|Write|NotebookEdit): checks what this call would leave; exit 2 blocks it.
Stop: checks the task directories this branch touches, committed or not, which also catches files made from the
shell; exit 2 keeps the agent working, once (`stop_hook_active`).
Stderr goes to the agent. Standard library only: it runs on whatever `python3` is on PATH.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

from _repo import adopted, checkouts

PLUGIN = Path(__file__).parents[1]
TEMPLATE = PLUGIN / "skills" / "analysis-workflow" / "assets" / "task_template"
TASK_DIR = re.compile(r".+_v\d+$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
#: A task-local environment, for a benchmark's candidates (the skill's Environments).
TASK_ENVIRONMENT = {"pixi.toml", "pixi.lock"}


def output_dirs() -> set[str]:
    """The task output directories, read from the package's `paths.py` without running it.

    The package targets a newer Python than this hook, and may not be installed.
    """
    names = ("TRACKED_TASK_DIRS", "UNTRACKED_TASK_DIRS")
    tree = ast.parse((PLUGIN / "src" / "analysis_workflow" / "paths.py").read_text())
    found = {
        target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in names
    }
    return {d for name in names for d in found[name]}


def allowed() -> set[str]:
    """What the top of a task directory may hold."""
    return {p.name for p in TEMPLATE.iterdir()} | output_dirs() | TASK_ENVIRONMENT


def headings(text: str) -> list[tuple[int, str]]:
    """(level, text) of each Markdown heading outside fenced code blocks."""
    found, fenced = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and (m := HEADING.match(line)):
            found.append((len(m.group(1)), m.group(2)))
    return found


def task_dir(path: Path, analysis: Path, entries: set[str]) -> Path | None:
    """The task directory ``path`` is in, below the checkout's `analysis/`.

    Walking down, the last directory named `<name>_vN` before the path enters one of a task's own ``entries``: a
    topic named like a task (`cohort_v1/demo_v1/`) is passed over, a versioned folder inside a task's outputs
    (`demo_v1/outputs/model_v1/`) is not taken for one.
    """
    if not path.is_relative_to(analysis):
        return None
    below, task = path.relative_to(analysis).parts[:-1], None
    for i, part in enumerate(below):
        if task is not None and part in entries:
            break
        if TASK_DIR.match(part):
            task = i
    return None if task is None else analysis.joinpath(*below[: task + 1])


def problem(path: Path, task: Path, entries: set[str], text: str | None) -> str | None:
    """What is off-layout about ``path`` in ``task``; ``text`` is the README's, when ``path`` is the README."""
    top = path.relative_to(task).parts[0]
    if top not in entries:
        return f"`{top}` is not part of a task directory, whose top holds only {', '.join(sorted(entries))}."
    if path != task / "README.md" or text is None:
        return None
    expected = [(1, task.name), *((n, h) for n, h in headings((TEMPLATE / "README.md").read_text()) if n > 1)]
    if headings(text) == expected:
        return None
    show = "\n".join(f"    {'#' * n} {h}" for n, h in expected)
    return f"the README must have exactly the template's headings, titled with the directory's name:\n{show}"


def after(tool_input: dict, path: Path) -> str | None:
    """The file's text once this Write or Edit is applied; None if it cannot be known."""
    if "content" in tool_input:
        return str(tool_input["content"])
    try:
        text = path.read_text()
    except OSError:
        return None
    old, new = str(tool_input.get("old_string", "")), str(tool_input.get("new_string", ""))
    return text.replace(old, new) if tool_input.get("replace_all") else text.replace(old, new, 1)


def check_write(tool_input: dict) -> list[str]:
    """The problems a file tool call would leave."""
    path = Path(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    if "analysis" not in path.parts:
        return []
    path = path.resolve()
    found = checkouts(path.parent)
    if not found or not adopted(found[0]):
        return []
    entries = allowed()
    task = task_dir(path, found[0].resolve() / "analysis", entries)
    why = task and problem(path, task, entries, after(tool_input, path))
    return [f"in {task.name}/, {why}"] if why else []


def git(top: Path, *args: str) -> str:
    """A git command's output in the checkout ``top``; empty if it fails."""
    return subprocess.run(["git", *args], cwd=top, capture_output=True, text=True, timeout=10).stdout


def branch_changes(top: Path) -> list[Path]:
    """Paths under `analysis/` this branch changed, committed or not, deleted ones included, and untracked files."""
    base = next((b for ref in ("origin/HEAD", "origin/main", "main") if (b := git(top, "merge-base", "HEAD", ref))), "")
    names = git(top, "diff", "--name-only", "--no-renames", "-z", base.strip() or "HEAD", "--", "analysis").split("\0")
    names += git(top, "ls-files", "--others", "--exclude-standard", "-z", "--", "analysis").split("\0")
    return [top / name for name in dict.fromkeys(names) if name]


def check_changes(cwd: Path) -> list[str]:
    """The problems in the task directories this branch touches, in the checkout at ``cwd``."""
    found = checkouts(cwd)
    if not found or not adopted(found[0]):
        return []
    top = found[0].resolve()
    entries, problems, tasks = allowed(), [], {}
    for path in branch_changes(top):
        if task := task_dir(path, top / "analysis", entries):
            tasks[task] = None
            if path.exists() and (why := problem(path, task, entries, None)):
                problems.append(f"in {task.name}/, {why}")
    for task in (t for t in tasks if t.is_dir()):  # a task renamed away is gone, not broken
        readme = task / "README.md"
        why = problem(readme, task, entries, readme.read_text()) if readme.exists() else "no README.md."
        if why:
            problems.append(f"in {task.name}/, {why}")
    return list(dict.fromkeys(problems))


def main() -> int:
    """Read the hook payload from stdin; return the exit code."""
    payload = json.load(sys.stdin)
    if payload.get("hook_event_name") == "Stop":
        if payload.get("stop_hook_active"):
            return 0
        problems = check_changes(Path(payload.get("cwd") or "."))
    else:
        problems = check_write(payload.get("tool_input", {}))
    if not problems:
        return 0
    for why in problems:
        print(f"Off the task layout: {why}", file=sys.stderr)
    print("See the analysis-workflow skill (Tasks) and its task template.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
