"""The PreToolUse hooks: a JSON payload on stdin in, an exit code out (2 = blocked)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).parents[1] / "hooks"


def run(hook: str, payload: dict) -> int:
    proc = subprocess.run([sys.executable, HOOKS / hook], input=json.dumps(payload), capture_output=True, text=True)
    return proc.returncode


def write(path: Path, content: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": content}}


@pytest.mark.parametrize(
    "content",
    [
        'OUT = "/home/me/repo/.claude/worktrees/wt/analysis/x"',
        'OUT = "/tmp/run1"',
        'OUT = "/scratch/tmp.123/out"',
        'OUT = Path("data/raw/x.zarr")',
        'OUT = Path("figures/fig1.pdf")',
    ],
)
def test_task_paths_blocks(repo, content):
    _, worktree = repo
    assert run("guard_task_paths.py", write(worktree / "analysis" / "t_v1" / "run.py", content)) == 2


def test_task_paths_blocks_absolute_paths_into_this_repo(repo):
    main, worktree = repo
    content = f'OUT = "/anywhere/{main.name}/analysis/x"'
    assert run("guard_task_paths.py", write(worktree / "analysis" / "t_v1" / "run.py", content)) == 2


@pytest.mark.parametrize(
    ("rel", "content"),
    [
        ("analysis/t_v1/run.py", "PATHS = task_paths(__file__)"),
        ("analysis/t_v1/README.md", 'OUT = "/tmp/run1"'),  # prose may quote paths
        ("src/pkg/io.py", 'OUT = "/tmp/run1"'),  # outside analysis/
    ],
)
def test_task_paths_allows(repo, rel, content):
    _, worktree = repo
    assert run("guard_task_paths.py", write(worktree / rel, content)) == 0


@pytest.fixture
def pixi_worktree(repo):
    _, worktree = repo
    (worktree / "pixi.toml").write_text('[pypi-dependencies]\nmyproject = { path = ".", editable = true }\n')
    task = worktree / "analysis" / "bench_v1"
    task.mkdir(parents=True)
    (task / "pixi.toml").write_text("[workspace]\n")
    return worktree


def bash(command: str, cwd: Path) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


@pytest.mark.parametrize(
    "command", ["pixi install", "pixi add numpy", "cd . && pixi lock", "pixi -v install", "pixi run python x.py"]
)
def test_pixi_blocks_root_workspace_of_a_worktree(pixi_worktree, command):
    assert run("guard_worktree_pixi.py", bash(command, pixi_worktree)) == 2


@pytest.mark.parametrize(
    ("command", "where"),
    [
        ("pixi list", "."),
        ("pixi install", "analysis/bench_v1"),  # task-local workspace
        ('gh pr create --body "run pixi install in main"', "."),  # quoted text
    ],
)
def test_pixi_allows(pixi_worktree, command, where):
    assert run("guard_worktree_pixi.py", bash(command, pixi_worktree / where)) == 0


def test_pixi_allows_running_on_the_main_checkouts_environment(repo, pixi_worktree):
    main, _ = repo
    command = f"pixi run --manifest-path {main}/pixi.toml python x.py"
    assert run("guard_worktree_pixi.py", bash(command, pixi_worktree)) == 0


def test_pixi_allows_the_main_checkout(repo):
    main, _ = repo
    (main / "pixi.toml").write_text('[pypi-dependencies]\nmyproject = { path = ".", editable = true }\n')
    assert run("guard_worktree_pixi.py", bash("pixi install", main)) == 0


def test_guards_ignore_repos_that_have_not_adopted_the_plugin(unadopted_repo):
    _, worktree = unadopted_repo
    (worktree / "pixi.toml").write_text('[pypi-dependencies]\nother = { path = ".", editable = true }\n')
    assert run("guard_task_paths.py", write(worktree / "analysis" / "t_v1" / "run.py", 'OUT = "/tmp/run1"')) == 0
    assert run("guard_worktree_pixi.py", bash("pixi install", worktree)) == 0


def session_start(cwd: Path) -> str:
    payload = json.dumps({"hook_event_name": "SessionStart", "cwd": str(cwd)})
    return subprocess.run(
        [sys.executable, HOOKS / "session_start.py"], input=payload, capture_output=True, text=True, check=True
    ).stdout


def test_session_start_prints_the_rules_only_in_an_adopted_repo(repo, unadopted_repo, tmp_path):
    main, worktree = repo
    rules = (HOOKS / "session_context.md").read_text()
    assert session_start(main) == session_start(worktree / "analysis") == rules
    assert session_start(unadopted_repo[0]) == session_start(tmp_path) == ""
