#!/usr/bin/env python3
"""Block shell copies and moves into a repo's shared storage, `data/<dataset>/processed/`.

An object enters shared storage from Python, inside `with writes(<store>):`, which records in the store which
task wrote it; a `cp`, `mv` or `rsync` leaves no record. `raw/` and `resources/` take data from outside the
repo and are left alone.

It acts only in a repo that has adopted the plugin. A destination the shell expands at run time is let
through: the guard is against accidents, not obfuscation.

PreToolUse hook (Bash): exit 2 blocks the call and shows stderr to the agent.
Standard library only: it runs on whatever `python3` is on PATH.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _repo import adopted, checkouts, how_to_lift, lifted, shell_calls

COMMANDS = frozenset({"cp", "mv", "rsync"})
#: Options of `cp` and `mv` that name the destination directory, in place of the last operand. To `rsync`, `-t`
#: means "keep modification times".
TARGET_OPTIONS = ("-t", "--target-directory")


def destination(name: str, args: list[str]) -> str | None:
    """Where a `cp`, `mv` or `rsync` call writes: for `cp` and `mv` its target option, or else its last operand."""
    for i, arg in enumerate(args if name != "rsync" else []):
        if arg in TARGET_OPTIONS and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--target-directory="):
            return arg.split("=", 1)[1]
    operands = []
    for arg in args:
        if arg in ("<", ">", ">>"):  # a redirection ends the call's own arguments
            break
        if not arg.startswith("-"):
            operands.append(arg)
    return operands[-1] if len(operands) > 1 else None


def into_shared_storage(target: str, cwd: Path, roots: tuple[Path, Path]) -> bool:
    """Whether ``target`` is under `data/<dataset>/processed/` of this checkout or the main one."""
    path = (cwd / target).resolve()
    for root in roots:
        data = root.resolve() / "data"
        if path.is_relative_to(data) and "processed" in path.relative_to(data).parts[1:2]:
            return True
    return False


def main() -> int:
    """Read the hook payload from stdin; return the exit code."""
    payload = json.load(sys.stdin)
    command = payload.get("tool_input", {}).get("command", "")
    if not any(name in command for name in COMMANDS):
        return 0
    cwd = Path(payload.get("cwd") or ".").resolve()
    found = checkouts(cwd)
    if not found or not adopted(found[0]):
        return 0
    for name, args in shell_calls(command, COMMANDS) or []:
        target = destination(name, args)
        if target is None or any(c in target for c in "$`") or not into_shared_storage(target, cwd, found):
            continue
        if "shared-writes" in lifted(payload):
            return 0
        print(
            f"Refused: `{name}` into shared storage ({target}).\n"
            "An object enters `data/<dataset>/processed/` from Python, inside a `writes` block, so the store\n"
            "records which task wrote it, and only after the human approved the write:\n"
            "    with writes(dest):\n"
            "        shutil.copytree(src, dest)\n"
            f"See the analysis-workflow skill (Tasks, Finish). {how_to_lift('shared-writes')}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
