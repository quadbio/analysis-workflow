"""The repository a hook acts on, and whether it has adopted the plugin.

The hooks act only in a checkout whose committed `.claude/settings.json` enables `analysis-workflow`, so the
plugin can be enabled for a user (which the skill's repo set-up needs) without touching their other repos.
Standard library only: it runs on whatever `python3` is on PATH.
"""

import json
import subprocess
from pathlib import Path

PLUGIN = "analysis-workflow"


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
