"""The plugin manifest and the Python package describe the same release."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_versions_agree():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    package = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert plugin["version"] == package["version"]


def test_hook_scripts_exist():
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    commands = [h["command"] for groups in hooks.values() for group in groups for h in group["hooks"]]
    for command in commands:
        script = command.split("${CLAUDE_PLUGIN_ROOT}/")[1].rstrip('"')
        assert (ROOT / script).is_file(), script
