"""The repository a hook acts on, and whether it has adopted the plugin.

The hooks act only in a checkout whose committed `.claude/settings.json` enables `analysis-workflow`, so the
plugin can be enabled for a user (which the skill's repo set-up needs) without touching their other repos.
Standard library only: it runs on whatever `python3` is on PATH.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

PLUGIN = "analysis-workflow"

#: `pixi` subcommands that change the workspace environment, or use it and so install it first if it is missing.
PIXI_ENV_COMMANDS = frozenset(
    {"install", "add", "lock", "upgrade", "update", "reinstall", "remove", "run", "shell", "shell-hook"}
)
#: The first of these after `pixi` is the command, whatever global options precede it.
PIXI_SUBCOMMANDS = PIXI_ENV_COMMANDS | {
    "auth", "build", "clean", "completion", "config", "exec", "global", "import", "info", "init", "list",
    "search", "self-update", "task", "tree", "upload", "workspace",
}  # fmt: skip


def checkouts(directory: Path) -> tuple[Path, Path] | None:
    """The checkout containing ``directory`` and the repository's main checkout; None outside git."""
    while not directory.is_dir():
        directory = directory.parent
    try:
        toplevel, common_dir = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.splitlines()
    except (subprocess.SubprocessError, OSError, ValueError):
        return None
    return Path(toplevel), Path(common_dir).parent


def adopted(checkout: Path) -> bool:
    """Whether the checkout's `.claude/settings.json` enables this plugin, from any marketplace."""
    try:
        enabled = json.loads((checkout / ".claude" / "settings.json").read_text()).get("enabledPlugins", {})
        return any(key.split("@")[0] == PLUGIN and on is True for key, on in enabled.items())
    except (OSError, ValueError, AttributeError):
        return False


def nearest_manifest(directory: Path) -> Path:
    """The `pixi.toml` pixi itself finds from ``directory``: the nearest at or above it."""
    return next(
        (d / "pixi.toml" for d in (directory, *directory.parents) if (d / "pixi.toml").exists()),
        directory / "pixi.toml",
    )


def is_root_of_worktree(manifest: Path) -> bool:
    """Whether ``manifest`` is the root workspace of a worktree of an adopted repo.

    Its editable self-dependency (`path = "."`) would rebase the repo's package, and every path it
    resolves, into the worktree. A task-local manifest is its own workspace.
    """
    if ".claude/worktrees" not in str(manifest):
        return False
    if manifest.exists() and 'path = "."' not in manifest.read_text(errors="ignore"):
        return False
    found = checkouts(manifest.parent)
    return found is not None and adopted(found[0])


def _is_separator(tok: str) -> bool:
    """A token made only of command separators (`;`, `&&`, `|`, newlines, parentheses)."""
    return bool(tok) and set(tok) <= set(";&|()\n")


def pixi_calls(command: str, comments: bool = False) -> list[list[str]] | None:
    """Argument lists of the `pixi` calls in ``command`` that change or use an environment; None if unparsable.

    With ``comments``, an unquoted `#` starts a comment to the end of its line, as in a script. Quotes are
    honoured either way, so quoted text (a PR body, an echoed message) is never read as a call.
    """
    tokens = []
    for text in command.splitlines(keepends=True) if comments else [command]:
        lexer = shlex.shlex(text, posix=True, punctuation_chars="();<>|&\n")
        lexer.whitespace = " \t\r"  # newlines separate commands, so keep them as tokens
        lexer.commenters = "#" if comments else ""  # one line at a time: a comment swallows its newline
        lexer.whitespace_split = True
        try:
            tokens += [*lexer, "\n"]
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
        if next((a for a in args if a in PIXI_SUBCOMMANDS), None) in PIXI_ENV_COMMANDS:
            calls.append(args)
    return calls


#: Options of `pixi run`, `shell` and `shell-hook` that take a value (from their `--help`).
PIXI_VALUE_OPTIONS = frozenset(
    {"-e", "--environment", "-p", "--platform", "-m", "--manifest-path", "-w", "--workspace", "-s", "--script",
     "--shell", "--config-file", "--auth-file", "--concurrent-downloads", "--concurrent-solves", "--pinning-strategy",
     "--pypi-keyring-provider", "--tls-root-certs", "--color", "--change-ps1"}
)  # fmt: skip


def pixi_options(args: list[str]) -> tuple[str | None, list[str]]:
    """A `pixi` call's subcommand and its own options. In `pixi run`, arguments after the task are the task's."""
    command = next((a for a in args if a in PIXI_SUBCOMMANDS), None)
    options, value_next = [], False
    for a in args[args.index(command) + 1 :] if command else args:
        if command == "run" and not value_next and not a.startswith("-"):
            break
        options.append(a)
        value_next = a in PIXI_VALUE_OPTIONS
    return command, options


def manifest_arg(args: list[str]) -> str | None:
    """The `--manifest-path` a pixi call passes, if any."""
    _, options = pixi_options(args)
    for i, a in enumerate(options):
        if a in ("--manifest-path", "-m"):
            return options[i + 1] if i + 1 < len(options) else None
        if a.startswith("--manifest-path="):
            return a.split("=", 1)[1]
    return None


def as_is(args: list[str]) -> bool:
    """Whether a `pixi` call uses an environment as it stands: `run`, `shell` or `shell-hook` with `--as-is`."""
    command, options = pixi_options(args)
    return command in {"run", "shell", "shell-hook"} and "--as-is" in options
