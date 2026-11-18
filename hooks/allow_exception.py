#!/usr/bin/env python3
"""Lift one guard for this session when the human types `/analysis-workflow:allow <guard>`.

UserPromptExpansion fires for a command the human types, and not for a skill the model loads, a scheduled prompt
or a message from a subagent or another session: only the human lifts a guard. The guard is recorded in the
session's marker (`_repo.py`), which the guards read and which outlives resume and compaction.

It acts only in a repo that has adopted the plugin. An unknown guard blocks the command and names the guards to
the human; otherwise stdout tells the agent what was lifted.
Standard library only: it runs on whatever `python3` is on PATH.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _repo import ALLOW, GUARDS, adopted, checkouts, lifted, marker


def main() -> int:
    """Read the hook payload from stdin; return the exit code."""
    payload = json.load(sys.stdin)
    if payload.get("command_name") != ALLOW:
        return 0
    found = checkouts(Path(payload.get("cwd") or ".").resolve())
    if not (found and adopted(found[0])):
        return 0
    guard, path = str(payload.get("command_args") or "").strip(), marker(payload)
    if guard not in GUARDS or path is None:
        why = f"no guard named `{guard}`; one of {', '.join(GUARDS)}." if path else "nowhere to record it."
        print(json.dumps({"decision": "block", "reason": f"analysis-workflow: {why}"}))
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{g}\n" for g in dict.fromkeys([*lifted(payload), guard])))
    print(
        f"The human lifted the `{guard}` guard for this session. What it now lets through is an exception to "
        "these conventions: note it as the repo's `CONVENTIONS.md` says."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
