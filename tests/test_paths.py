import pytest

from analysis_workflow import main_checkout, task_paths


def test_main_checkout_from_a_worktree(repo):
    main, worktree = repo
    assert main_checkout(worktree / "analysis") == main.resolve()
    assert main_checkout(main / "analysis") == main.resolve()


def test_main_checkout_from_a_file_that_does_not_exist_yet(repo):
    main, worktree = repo
    assert main_checkout(worktree / "analysis" / "new_v1" / "scripts" / "_common.py") == main.resolve()


def test_main_checkout_outside_git_raises(tmp_path):
    with pytest.raises(RuntimeError, match="not inside a git checkout"):
        main_checkout(tmp_path)


def test_task_paths_split(repo):
    """Tracked dirs stay in the calling checkout; untracked ones go to the main checkout."""
    main, worktree = repo
    paths = task_paths(worktree / "analysis" / "topic" / "demo_v1" / "scripts" / "_common.py")

    task = (worktree / "analysis" / "topic" / "demo_v1").resolve()
    main_task = main.resolve() / "analysis" / "topic" / "demo_v1"
    assert paths.task == task
    assert (paths.results, paths.reports) == (task / "results", task / "reports")
    assert (paths.figures, paths.outputs, paths.logs) == (
        main_task / "figures",
        main_task / "outputs",
        main_task / "logs",
    )


def test_task_root_and_scripts_agree(repo):
    _, worktree = repo
    task = worktree / "analysis" / "topic" / "demo_v1"
    assert task_paths(task / "_common.py") == task_paths(task / "scripts" / "_common.py")


@pytest.mark.parametrize("rel", ["analysis/_common.py", "elsewhere/demo_v1/_common.py"])
def test_rejects_files_outside_a_task(repo, rel):
    _, worktree = repo
    with pytest.raises(ValueError, match="analysis"):
        task_paths(worktree / rel)


def test_ensure_creates_dirs_and_resolving_does_not(repo):
    _, worktree = repo
    paths = task_paths(worktree / "analysis" / "topic" / "demo_v1" / "_common.py")
    dirs = (paths.results, paths.reports, paths.figures, paths.outputs, paths.logs)
    assert not any(d.exists() for d in dirs)
    paths.ensure()
    assert all(d.is_dir() for d in dirs)
