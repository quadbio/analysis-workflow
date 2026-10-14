"""The PreToolUse hooks: a JSON payload on stdin in, an exit code out (2 = blocked)."""

import json
import os
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


def test_pixi_allows_running_on_the_main_checkouts_environment_as_is(repo, pixi_worktree):
    main, _ = repo
    command = f"pixi run --manifest-path {main}/pixi.toml --as-is python x.py"
    assert run("guard_worktree_pixi.py", bash(command, pixi_worktree)) == 0
    command = f"pixi run -e gpu --manifest-path {main}/pixi.toml --as-is python x.py"  # an option's value is no task
    assert run("guard_worktree_pixi.py", bash(command, pixi_worktree)) == 0
    lock_checkout = main.parent / f"{main.name}-lock"  # where a task changes the environment
    assert (
        run("guard_worktree_pixi.py", bash(f"pixi lock --manifest-path {lock_checkout}/pixi.toml", pixi_worktree)) == 0
    )


@pytest.mark.parametrize(
    "call",
    [
        "run --manifest-path {main}/pixi.toml python x.py",
        "run --manifest-path {main}/pixi.toml python x.py --as-is",  # after the task, the flag is the task's
        "install --manifest-path {main}/pixi.toml",
        "shell-hook -m {main}",
    ],
)
def test_pixi_blocks_main_checkouts_environment_unless_as_is(repo, pixi_worktree, call):
    main, _ = repo
    assert run("guard_worktree_pixi.py", bash("pixi " + call.format(main=main), pixi_worktree)) == 2


@pytest.mark.parametrize(
    "line",
    [
        "pixi run python scripts/a.py",
        "srun -n1 pixi run python a.py",
        "pixi install",
        "pixi \\\n    run python a.py",  # continued line
        "pixi run --manifest-path ../../../pixi.toml python a.py",  # resolves against the job's directory
        'pixi run python a.py && pixi run --manifest-path "$MAIN/pixi.toml" python b.py',  # each call checked
        "pixi update",
        'ROOT=$(git rev-parse --show-toplevel); pixi run --manifest-path "$ROOT/pixi.toml" python a.py',
        'pixi run python a.py  # TODO: --manifest-path "$MAIN/pixi.toml"',
        'echo "starting # job"; pixi run python a.py',  # a quoted hash is no comment
        'pixi run python a.py --manifest-path "$MAIN/pixi.toml"',  # after the task, the flag is the task's
        'pixi run --manifest-path "$MAIN/pixi.toml" python a.py',  # without --as-is it may install into main
        'pixi run --manifest-path "$MAIN/pixi.toml" python a.py --as-is',  # the task's flag, not pixi's
    ],
)
def test_task_paths_blocks_job_scripts_running_pixi_on_the_worktree(pixi_worktree, line):
    job = pixi_worktree / "analysis" / "t_v1" / "scripts" / "run.sh"
    assert run("guard_task_paths.py", write(job, f"#!/bin/bash\n{line}\n")) == 2


@pytest.mark.parametrize(
    ("rel", "line"),
    [
        ("analysis/t_v1/scripts/run.sh", 'pixi run --manifest-path "$MAIN/pixi.toml" --as-is python scripts/a.py'),
        ("analysis/t_v1/scripts/run.sh", "pixi run --as-is --manifest-path=${MAIN}/pixi.toml python scripts/a.py"),
        ("analysis/t_v1/scripts/run.sh", 'pixi run -e gpu --manifest-path "$MAIN/pixi.toml" --as-is python a.py'),
        ("analysis/t_v1/scripts/run.sh", "# not pixi run python a.py, see the README"),
        ("analysis/bench_v1/run.sh", "pixi run python a.py"),  # task-local workspace
        ("analysis/t_v1/scripts/run.py", 'print("pixi run python a.py")'),  # not a job script
    ],
)
def test_task_paths_allows_job_scripts(pixi_worktree, rel, line):
    assert run("guard_task_paths.py", write(pixi_worktree / rel, f"#!/bin/bash\n{line}\n")) == 0


def test_pixi_allows_the_main_checkout(repo):
    main, _ = repo
    (main / "pixi.toml").write_text('[pypi-dependencies]\nmyproject = { path = ".", editable = true }\n')
    assert run("guard_worktree_pixi.py", bash("pixi install", main)) == 0


def test_guards_ignore_repos_that_have_not_adopted_the_plugin(unadopted_repo):
    _, worktree = unadopted_repo
    (worktree / "pixi.toml").write_text('[pypi-dependencies]\nother = { path = ".", editable = true }\n')
    assert run("guard_task_paths.py", write(worktree / "analysis" / "t_v1" / "run.py", 'OUT = "/tmp/run1"')) == 0
    assert run("guard_worktree_pixi.py", bash("pixi install", worktree)) == 0


def session_start(cwd: Path, **env: str) -> str:
    payload = json.dumps({"hook_event_name": "SessionStart", "cwd": str(cwd)})
    environ = {k: v for k, v in os.environ.items() if k != "CLAUDE_ENV_FILE"} | env
    return subprocess.run(
        [sys.executable, HOOKS / "session_start.py"],
        input=payload,
        capture_output=True,
        text=True,
        check=True,
        env=environ,
    ).stdout


def test_session_start_prints_the_rules_only_in_an_adopted_repo(repo, unadopted_repo, tmp_path):
    main, worktree = repo
    rules = (HOOKS / "session_context.md").read_text()
    assert session_start(main).startswith(rules)
    assert session_start(worktree / "analysis").startswith(rules)
    assert session_start(unadopted_repo[0]) == session_start(tmp_path) == ""


@pytest.fixture
def fake_pixi(repo, tmp_path):
    """A `pixi` whose `shell-hook --json` activates ``prefix``; the main checkout has a manifest."""
    main, worktree = repo
    (main / "pixi.toml").write_text("[workspace]\n")
    (worktree / "src").mkdir()
    prefix = tmp_path / "env"
    prefix.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    variables = {
        "CONDA_PREFIX": str(prefix),
        "PATH": f"{prefix}/bin:/usr/bin",
        "WITH_QUOTE": "it's",
        "PYTHONPATH": "/act",
    }
    pixi = bin_dir / "pixi"
    pixi.write_text(f"#!{sys.executable}\nprint({json.dumps(json.dumps({'environment_variables': variables}))})\n")
    pixi.chmod(0o755)
    return {"PATH": f"{bin_dir}:{os.environ['PATH']}"}, prefix


def sourced(env_file: Path, name: str) -> str:
    return subprocess.run(
        ["bash", "-c", f'source "{env_file}"; printf %s "${name}"'], capture_output=True, text=True, check=True
    ).stdout


def test_session_start_activates_the_main_environment(repo, fake_pixi, tmp_path):
    main, worktree = repo
    path, prefix = fake_pixi
    env_file = tmp_path / "env.sh"
    env_file.write_text("export OTHER_HOOK=1\n")
    for _ in range(2):  # startup, then resume or compaction
        out = session_start(worktree, CLAUDE_ENV_FILE=str(env_file), **path)
    assert f"runs on `{prefix}`" in out
    text = env_file.read_text()
    assert text.count("OTHER_HOOK") == text.count("analysis-workflow: main environment") == 1
    assert sourced(env_file, "CONDA_PREFIX") == str(prefix)
    assert sourced(env_file, "WITH_QUOTE") == "it's"
    assert sourced(env_file, "PYTHONPATH") == f"{worktree / 'src'}{os.pathsep}/act"  # activation's value kept

    main_env = tmp_path / "main.sh"
    session_start(main, CLAUDE_ENV_FILE=str(main_env), **path)
    assert sourced(main_env, "PYTHONPATH") == "/act"


def test_session_start_without_an_installed_environment(repo, fake_pixi, tmp_path):
    _, worktree = repo
    path, prefix = fake_pixi
    env_file = tmp_path / "env.sh"
    env_file.write_text("export OTHER_HOOK=1\n")
    session_start(worktree, CLAUDE_ENV_FILE=str(env_file), **path)
    prefix.rmdir()  # removed before a resume or compaction reruns the hook
    assert "No environment is active" in session_start(worktree, CLAUDE_ENV_FILE=str(env_file), **path)
    assert env_file.read_text() == "export OTHER_HOOK=1\n"
    fresh = tmp_path / "fresh.sh"
    session_start(worktree, CLAUDE_ENV_FILE=str(fresh), **path)
    assert not fresh.exists()
    assert "No environment is active" in session_start(worktree, **path)  # no CLAUDE_ENV_FILE
