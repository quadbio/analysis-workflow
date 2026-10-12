#!/usr/bin/env python3
"""Print the always-on core rules at session start, in a repo that has adopted the plugin.

SessionStart hook: stdout is added to the agent's context.
Standard library only: it runs on whatever `python3` is on PATH.
"""

import json
import sys
from pathlib import Path

from _repo import adopted, checkouts


def main() -> int:
    """Read the hook payload from stdin; return the exit code."""
    found = checkouts(Path(json.load(sys.stdin).get("cwd") or ".").resolve())
    if found and adopted(found[0]):
        print((Path(__file__).parent / "session_context.md").read_text(), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
