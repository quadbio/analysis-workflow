#!/usr/bin/env python3
"""Keep every task directory in the template's layout.

A task directory (`analysis/<topic>/.../<name>_vN/`) holds at its top only what the task template holds
(`skills/analysis-workflow/assets/task_template/`) and the output directories of `task_paths`. Its README's title
is the directory's name, and its other headings are the template README's, all of them and in order. Both are read
from their sources, the template and `paths.py`, so a change there is a change here. Only the text this call would
leave in the file is checked.

PreToolUse hook (Edit|Write|NotebookEdit): exit 2 blocks the call and shows stderr to the agent.
Standard library only: it runs on whatever `python3` is on PATH.
"""

from __future__ import annotations

import ast
import json
import re
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


def headings(text: str) -> list[tuple[int, str]]:
    """(level, text) of each Markdown heading outside fenced code blocks."""
    found, fenced = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and (m := HEADING.match(line)):
            found.append((len(m.group(1)), m.group(2)))
    return found


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


def task_dir(path: Path, analysis: Path) -> Path | None:
    """The task directory ``path`` is in: the outermost directory named `<name>_vN` under the checkout's `analysis/`.

    Outermost, so a versioned folder inside a task (`outputs/model_v1/`) is not taken for one.
    """
    if not path.is_relative_to(analysis):
        return None
    below = path.relative_to(analysis).parts[:-1]
    return next((analysis.joinpath(*below[: i + 1]) for i, p in enumerate(below) if TASK_DIR.match(p)), None)


def problem(path: Path, task: Path, tool_input: dict) -> str | None:
    """What is off-layout about this call, or None."""
    top = path.relative_to(task).parts[0]
    allowed = {p.name for p in TEMPLATE.iterdir()} | output_dirs() | TASK_ENVIRONMENT
    if top not in allowed:
        return f"`{top}` is not part of a task directory, whose top holds only {', '.join(sorted(allowed))}."
    if path != task / "README.md" or (text := after(tool_input, path)) is None:
        return None
    expected = [(1, task.name), *((n, h) for n, h in headings((TEMPLATE / "README.md").read_text()) if n > 1)]
    actual = headings(text)
    if actual == expected:
        return None
    show = "\n".join(f"    {'#' * n} {h}" for n, h in expected)
    return f"the README must have exactly the template's headings, titled with the directory's name:\n{show}"


def main() -> int:
    """Read the hook payload from stdin; return the exit code."""
    tool_input = json.load(sys.stdin).get("tool_input", {})
    path = Path(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    if "analysis" not in path.parts:
        return 0
    path = path.resolve()
    found = checkouts(path.parent)
    if not found or not adopted(found[0]) or (task := task_dir(path, found[0].resolve() / "analysis")) is None:
        return 0
    if (why := problem(path, task, tool_input)) is None:
        return 0
    print(f"Refused: in {task.name}/, {why}", file=sys.stderr)
    print("See the analysis-workflow skill (Tasks) and its task template.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
