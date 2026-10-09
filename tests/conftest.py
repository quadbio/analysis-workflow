import subprocess

import pytest


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A main checkout with one committed task, and a worktree of it under .claude/worktrees/."""
    return make_repo(tmp_path / "myproject")


@pytest.fixture
def repo_under_analysis(tmp_path):
    """As ``repo``, but inside an unrelated directory that is also named ``analysis``."""
    return make_repo(tmp_path / "analysis" / "myproject")


def make_repo(main):
    task = main / "analysis" / "topic" / "demo_v1"
    task.mkdir(parents=True)
    (task / "README.md").write_text("# demo_v1\n")
    git("init", "-b", "main", cwd=main)
    git("-c", "user.name=t", "-c", "user.email=t@t", "add", ".", cwd=main)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init", cwd=main)
    worktree = main / ".claude" / "worktrees" / "wt"
    git("worktree", "add", "-b", "wt", str(worktree), cwd=main)
    return main, worktree
