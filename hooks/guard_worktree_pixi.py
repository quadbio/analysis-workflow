#!/usr/bin/env python3
"""Block `pixi` commands that build or change an environment on the ROOT workspace of a git worktree.

An analysis repo's root `pixi.toml` declares its own package as an editable path dependency
(`path = "."`), so installing from a worktree rebases that package, and every path it resolves,
into the worktree. `pixi run` and `pixi shell` install that environment on first use, so they are
blocked too: a worktree runs on the main checkout's environment. Allowed through:

- a task-local manifest (no `path = "."`), which is its own workspace;
- `--manifest-path` pointing outside `.claude/worktrees` (the main checkout, or a sibling
  checkout used to change the environment), where `path = "."` resolves correctly.

It acts only in a repo that has adopted the plugin. Any unquoted `pixi` token counts, wherever it
stands; words inside quoted text (a PR body) do not. The guard is against accidents, not obfuscation,
and errs towards blocking.

PreToolUse hook (Bash): exit 2 blocks the call and shows stderr to the agent.
Standard library only: it runs on whatever `python3` is on PATH.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from _repo import PIXI_ENV_COMMANDS, adopted, checkouts, is_root_of_worktree, manifest_arg, nearest_manifest, pixi_calls


def _manifest(args: list[str], cwd: Path) -> Path | None:
    """The manifest a call acts on; None if it is only known at run time."""
    named = manifest_arg(args)
    if named is None:
        return nearest_manifest(cwd)
    if any(c in named for c in "$`"):
        return None  # shell-expanded at run time, so not provably outside a worktree
    path = Path(named)
    path = (cwd / path).resolve() if not path.is_absolute() else path.resolve()
    return path / "pixi.toml" if path.is_dir() else path


def _in_adopted_repo(directory: Path) -> bool:
    found = checkouts(directory)
    return found is not None and adopted(found[0])


def main() -> int:
    """Read the hook payload from stdin; return the exit code."""
    payload = json.load(sys.stdin)
    command = payload.get("tool_input", {}).get("command", "")
    cwd = Path(payload.get("cwd") or ".").resolve()

    if ".claude/worktrees" not in str(cwd) and "--manifest-path" not in command and " -m " not in command:
        return 0
    calls = pixi_calls(command)
    if calls is None:  # unparsable: fall back to the conservative text match
        pattern = rf"\bpixi\b.*\b({'|'.join(PIXI_ENV_COMMANDS)})\b"
        blocked = ".claude/worktrees" in str(cwd) and re.search(pattern, command) and _in_adopted_repo(cwd)
    else:
        manifests = [_manifest(args, cwd) for args in calls]
        blocked = any(_in_adopted_repo(cwd) if m is None else is_root_of_worktree(m) for m in manifests)
    if not blocked:
        return 0

    print(
        "Refused: a `pixi` command that builds or changes an environment on a worktree's root workspace.\n"
        "The root manifest's editable self-dependency (`path = \".\"`) would rebase the repo's package,\n"
        "and every path it resolves, into this worktree.\n"
        "  - to run something: python <script> (this session runs on the main checkout's environment),\n"
        "    or pixi run --manifest-path <main checkout>/pixi.toml --as-is python <script>\n"
        "  - to change the environment: lock and install it in a temporary checkout beside the main one\n"
        "    (skill, Environments); installing the MAIN checkout's environment is the human's.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
