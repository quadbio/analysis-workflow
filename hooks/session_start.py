#!/usr/bin/env python3
"""In a repo that has adopted the plugin: print the core rules, and activate the main checkout's environment.

SessionStart hook: stdout is added to the agent's context. Claude Code runs the file named by `$CLAUDE_ENV_FILE`
before each Bash command, subagents' included, and keeps it across resume and compaction, when this hook runs again
and replaces its own block. `--as-is` never installs or relocks. A worktree's `src/` goes first on `PYTHONPATH`, so
its edits to the repo's own package are imported.
Standard library only: it runs on whatever `python3` is on PATH.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from _repo import adopted, checkouts

BEGIN, END = "# analysis-workflow: main environment", "# analysis-workflow: end"


def activation(toplevel: Path, main: Path) -> dict[str, str]:
    """The variables that activate the main checkout's default environment; empty if it is not installed."""
    try:
        variables = json.loads(
            subprocess.run(
                ["pixi", "shell-hook", "--manifest-path", str(main / "pixi.toml"), "--as-is", "--json"],
                capture_output=True,
                text=True,
                timeout=20,  # under the hook's own 30 s in hooks.json
                check=True,
            ).stdout
        )["environment_variables"]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return {}
    if not Path(variables.get("CONDA_PREFIX", "")).is_dir():
        return {}
    if toplevel != main and (toplevel / "src").is_dir():
        outer = variables.get("PYTHONPATH", os.environ.get("PYTHONPATH"))  # activation's value wins, as in pixi
        variables["PYTHONPATH"] = os.pathsep.join(filter(None, [str(toplevel / "src"), outer]))
    return variables


def write_block(env_file: Path, variables: dict[str, str]) -> None:
    """Replace this hook's block in ``env_file``, or drop it if ``variables`` is empty; keep what other hooks wrote."""
    old = env_file.read_text() if env_file.exists() else ""
    kept = re.sub(rf"{re.escape(BEGIN)}\n.*?{re.escape(END)}\n", "", old, flags=re.DOTALL)
    exports = "".join(f"export {k}={shlex.quote(v)}\n" for k, v in variables.items() if k.isidentifier())
    if old or exports:
        env_file.write_text(f"{kept}{BEGIN}\n{exports}{END}\n" if exports else kept)


def main() -> int:
    """Read the hook payload from stdin; return the exit code."""
    found = checkouts(Path(json.load(sys.stdin).get("cwd") or ".").resolve())
    if not (found and adopted(found[0])):
        return 0
    print((Path(__file__).parent / "session_context.md").read_text(), end="")
    toplevel, main_checkout = found
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    variables = activation(toplevel, main_checkout) if env_file and (main_checkout / "pixi.toml").exists() else {}
    if env_file:
        write_block(Path(env_file), variables)  # a failed refresh on resume or compaction drops a stale block
    if variables:
        print(f"\nEvery Bash command runs on `{variables['CONDA_PREFIX']}`: run `python …` directly.")
    else:
        print(f"\nNo environment is active: run `pixi run --manifest-path {main_checkout}/pixi.toml --as-is …`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
