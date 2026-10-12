#!/usr/bin/env python3
"""Block `pixi` commands that build or change an environment on the ROOT workspace of a git worktree.

An analysis repo's root `pixi.toml` declares its own package as an editable path dependency
(`path = "."`), so installing from a worktree rebases that package, and every path it resolves,
into the worktree. `pixi run` and `pixi shell` install that environment on first use, so they are
blocked too: a worktree runs on the main checkout's environment. Allowed through:

- a task-local manifest (no `path = "."`), which is its own workspace;
- `--manifest-path` pointing outside `.claude/worktrees` (the main checkout, or a sibling
  checkout used to regenerate the lock), where `path = "."` resolves correctly.

It acts only in a repo that has adopted the plugin. Any unquoted `pixi` token counts, wherever it
stands; words inside quoted text (a PR body) do not. The guard is against accidents, not obfuscation,
and errs towards blocking.

PreToolUse hook (Bash): exit 2 blocks the call and shows stderr to the agent.
Standard library only: it runs on whatever `python3` is on PATH.
"""

import json
import re
import shlex
import sys
from pathlib import Path

from _repo import adopted, checkouts

_MUTATING = {"install", "add", "lock", "upgrade", "update", "reinstall", "remove"}
# These use the workspace environment, installing it first if it is missing.
_ENV_USING = {"run", "shell", "shell-hook"}
_BLOCKED = _MUTATING | _ENV_USING
# The first of these after `pixi` is the command, whatever global options precede it.
_SUBCOMMANDS = _BLOCKED | {
    "auth", "build", "clean", "completion", "config", "exec", "global", "import", "info", "init", "list",
    "search", "self-update", "task", "tree", "upload", "workspace",
}  # fmt: skip


def _is_separator(tok: str) -> bool:
    """A token made only of command separators (`;`, `&&`, `|`, newlines, parentheses)."""
    return bool(tok) and set(tok) <= set(";&|()\n")


def _pixi_calls(command: str) -> list[list[str]] | None:
    """Argument lists of blocked `pixi` calls; None if unparsable."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"  # newlines separate commands, so keep them as tokens
    lexer.commenters = ""  # a `#` comment must not swallow the newline after it
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    calls = []
    for i, tok in enumerate(tokens):
        if Path(tok).name != "pixi":
            continue
        args = []
        for t in tokens[i + 1 :]:
            if _is_separator(t):
                break
            args.append(t)
        if next((a for a in args if a in _SUBCOMMANDS), None) in _BLOCKED:
            calls.append(args)
    return calls


def _manifest(args: list[str], cwd: Path) -> Path | None:
    """The manifest a call acts on; None if it is only known at run time."""
    for i, a in enumerate(args):
        if a in ("--manifest-path", "-m") and i + 1 < len(args):
            path = Path(args[i + 1])
            break
        if a.startswith("--manifest-path="):
            path = Path(a.split("=", 1)[1])
            break
    else:  # pixi's own discovery: the nearest pixi.toml at or above cwd
        return next((d / "pixi.toml" for d in (cwd, *cwd.parents) if (d / "pixi.toml").exists()), cwd / "pixi.toml")
    if any(c in str(path) for c in "$`"):
        return None  # shell-expanded at run time, so not provably outside a worktree
    path = (cwd / path).resolve() if not path.is_absolute() else path.resolve()
    return path / "pixi.toml" if path.is_dir() else path


def _is_root_of_worktree(manifest: Path) -> bool:
    if ".claude/worktrees" not in str(manifest):
        return False
    if manifest.exists() and 'path = "."' not in manifest.read_text(errors="ignore"):
        return False  # task-local workspace
    return _in_adopted_repo(manifest.parent)


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
    calls = _pixi_calls(command)
    if calls is None:  # unparsable: fall back to the conservative text match
        pattern = rf"\bpixi\b.*\b({'|'.join(_BLOCKED)})\b"
        blocked = ".claude/worktrees" in str(cwd) and re.search(pattern, command) and _in_adopted_repo(cwd)
    else:
        manifests = [_manifest(args, cwd) for args in calls]
        blocked = any(_in_adopted_repo(cwd) if m is None else _is_root_of_worktree(m) for m in manifests)
    if not blocked:
        return 0

    print(
        "Refused: a `pixi` command that builds or changes an environment on a worktree's root workspace.\n"
        "The root manifest's editable self-dependency (`path = \".\"`) would rebase the repo's package,\n"
        "and every path it resolves, into this worktree.\n"
        "  - to run something: pixi run --manifest-path <main checkout>/pixi.toml python <script>\n"
        "  - to change the environment: do it in the MAIN checkout, one session at a time;\n"
        "    from a worktree, hand the command to the human.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
