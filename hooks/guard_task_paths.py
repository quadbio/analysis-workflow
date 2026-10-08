#!/usr/bin/env python3
"""Block path literals in analysis code that resolve to the wrong tree, or to no tree at all.

Every output path under `analysis/` comes from `task_paths(__file__)`, because a bare relative
write from a worktree lands in the worktree and disappears when it is removed, and worktrees are
usually gitignored, so git never warns. Absolute paths into a worktree, a temp dir or the checkout
itself outlive what they point at, or break on the next machine.

Only the text being written is inspected, so pre-existing violations elsewhere in a file do not
trip the hook; they surface when that line is next touched, which is when to fix them.

PreToolUse hook (Edit|Write|NotebookEdit): exit 2 blocks the call and shows stderr to the agent.
Standard library only: it runs on whatever `python3` is on PATH.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

# Code that runs. Prose may legitimately quote any of these paths.
CODE_SUFFIXES = {".py", ".sh", ".sbatch", ".ipynb", ".R"}


def _main_checkout_name(path: Path) -> str | None:
    directory = path.parent
    while not directory.is_dir():
        directory = directory.parent
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None
    return Path(out).parent.name


def _rules(repo: str | None) -> list[tuple[re.Pattern, str, str]]:
    """(pattern, what is wrong, the safe path)."""
    rules = [
        (
            re.compile(r"\.claude/worktrees/"),
            "a path into a git worktree",
            "worktrees are removed; task_paths(__file__) anchors figures/outputs/logs to the MAIN checkout",
        ),
        (
            re.compile(r"/tmp[./]"),
            "a path into a temp directory",
            "temp dirs are transient and per-machine; write to PATHS.figures or PATHS.outputs",
        ),
        (
            re.compile(r"""Path\(\s*["'](data|figures)/"""),
            "a path relative to the current working directory",
            "it only resolves when run from the repo root; use the repo's FilePaths constants",
        ),
    ]
    if repo:
        rules.append(
            (
                re.compile(rf"""["'](/[^"'\n]*/{re.escape(repo)}/)"""),
                "an absolute path into a checkout of this repo",
                "checkouts move and differ per worktree; use FilePaths for data, task_paths(__file__) for outputs",
            )
        )
    return rules


def main() -> int:
    """Read the hook payload from stdin; return the exit code."""
    tool_input = json.load(sys.stdin).get("tool_input", {})
    file_path = Path(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    if "analysis" not in file_path.parts or file_path.suffix not in CODE_SUFFIXES:
        return 0

    # Whatever this call would add: Write.content, Edit.new_string, NotebookEdit.new_source
    written = "\n".join(str(tool_input.get(key, "")) for key in ("content", "new_string", "new_source"))
    hits = [(what, fix) for pattern, what, fix in _rules(_main_checkout_name(file_path)) if pattern.search(written)]
    if not hits:
        return 0

    print(f"Refused: {file_path.name} would contain {', and '.join(what for what, _ in hits)}.", file=sys.stderr)
    for _, fix in hits:
        print(f"  -> {fix}", file=sys.stderr)
    print("See the analysis-workflow skill (task outputs).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
