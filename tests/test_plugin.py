"""The plugin manifest points at files that exist."""

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_hook_scripts_exist():
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    commands = [h["command"] for groups in hooks.values() for group in groups for h in group["hooks"]]
    for command in commands:
        script = command.split("${CLAUDE_PLUGIN_ROOT}/")[1].rstrip('"')
        assert (ROOT / script).is_file(), script
