import subprocess

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
