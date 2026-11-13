import os
import subprocess

import pytest
from typer.testing import CliRunner

from analysis_workflow.cli import HEAVY_RESULT_BYTES, app, heavy_tracked, orphaned_outputs, stray_worktree_outputs


def test_stray_output_in_a_worktree(repo):
    main, worktree = repo
    (worktree / "analysis" / "topic" / "demo_v1" / "figures").mkdir()
    (worktree / "analysis" / "topic" / "demo_v1" / "figures" / "fig1.pdf").write_text("x")
    # tooling that keeps its own logs/ is not a task
    (worktree / "analysis" / ".pixi" / "logs").mkdir(parents=True)
    (worktree / "analysis" / ".pixi" / "logs" / "x.log").write_text("x")
    assert stray_worktree_outputs(main) == [worktree / "analysis" / "topic" / "demo_v1" / "figures"]


def test_orphaned_output_in_main(repo):
    main, _ = repo
    for task in ("topic/demo_v1", "topic/deleted_v1"):
        out = main / "analysis" / task / "outputs"
        out.mkdir(parents=True)
        (out / "a.zarr").write_text("x")
    assert [p.relative_to(main).as_posix() for p in orphaned_outputs(main)] == ["analysis/topic/deleted_v1/outputs"]


def test_heavy_tracked_result(repo):
    main, _ = repo
    results = main / "analysis" / "topic" / "demo_v1" / "results"
    results.mkdir()
    (results / "big.csv").write_bytes(b"0" * (HEAVY_RESULT_BYTES + 1))
    subprocess.run(["git", "add", "-f", "."], cwd=main, check=True)
    assert [rel.name for rel, _, _ in heavy_tracked(main)] == ["big.csv"]


def test_layout_command(repo):
    _, worktree = repo
    result = CliRunner().invoke(app, ["check", "layout", str(worktree)])
    assert result.exit_code == 0, result.output
    assert "Clean." in result.output


def new(*args, cwd):
    old = os.getcwd()
    os.chdir(cwd)
    try:
        return CliRunner().invoke(app, ["new", *args])
    finally:
        os.chdir(old)


def test_new_task_from_the_template(repo):
    main, _ = repo
    result = new("analysis/ds/topic/human_markers_v1", "--author", "ML", cwd=main)
    assert result.exit_code == 0, result.output
    task = main / "analysis" / "ds" / "topic" / "human_markers_v1"
    readme = (task / "README.md").read_text().splitlines()
    assert readme[0] == "# human_markers_v1"
    assert readme[2].startswith("**Date:** 20") and readme[3] == "**Author:** ML"
    assert (task / "scripts" / "_common.py").is_file()
    assert (task / "notebooks").is_dir() and not any((task / "notebooks").iterdir())


@pytest.mark.parametrize(
    ("existing", "name", "message"),
    [
        ([], "human_markers_v2", "is v1, not v2"),
        (["human_markers_v1"], "agent_markers_v1", "is v2, not v1"),
        (["markers_v1", "agent_markers_v2"], "human_markers_v2", "is v3"),
        ([], "markers_v1", "not a task name"),
        ([], "robot_markers_v1", "not a task name"),
        (["human_markers_v1"], "human_markers_v1", "already exists"),
    ],
)
def test_new_task_refuses(repo, existing, name, message):
    main, _ = repo
    for d in existing:
        (main / "analysis" / "ds" / "topic" / d).mkdir(parents=True)
    result = new(f"analysis/ds/topic/{name}", "--author", "ML", cwd=main)
    assert result.exit_code == 1 and message in result.output, result.output


def test_new_task_counts_versions_in_the_main_checkout(repo):
    """An agent's worktree may not have a human's task yet; the main checkout does."""
    main, worktree = repo
    (main / "analysis" / "ds" / "topic" / "human_markers_v1").mkdir(parents=True)
    assert new("analysis/ds/topic/agent_markers_v1", "--author", "x", cwd=worktree).exit_code == 1
    assert new("analysis/ds/topic/agent_markers_v2", "--author", "x", cwd=worktree).exit_code == 0


def test_new_task_needs_a_dataset_and_topic(repo):
    main, _ = repo
    assert "not of the form" in new("analysis/human_markers_v1", "--author", "ML", cwd=main).output


def test_new_task_with_a_starter_notebook(repo):
    main, _ = repo
    assert (
        "no starter notebook"
        in new("analysis/ds/t/human_a_v1", "--author", "ML", "--notebook", "01_qc", cwd=main).output
    )
    assert not (main / "analysis" / "ds" / "t" / "human_a_v1").exists()

    (main / "templates").mkdir()
    (main / "templates" / "notebook.ipynb").write_text("{}")
    assert (
        "not a notebook name" in new("analysis/ds/t/human_a_v1", "--author", "ML", "--notebook", "qc", cwd=main).output
    )
    result = new("analysis/ds/t/human_a_v1", "--author", "ML", "--notebook", "01_qc", cwd=main)
    assert result.exit_code == 0, result.output
    assert (main / "analysis" / "ds" / "t" / "human_a_v1" / "notebooks" / "01_qc.ipynb").read_text() == "{}"
