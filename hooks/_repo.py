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
