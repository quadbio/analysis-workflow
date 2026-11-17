"""Tracing an artifact back through store records and declared inputs."""

import os
import shutil
import time

import anndata as ad
import numpy as np
import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from analysis_workflow import commit_adata, writes
from analysis_workflow.cli import app
from analysis_workflow.paths import task_id
from analysis_workflow.trace import changed_since_declared, declared, missing_inputs, trace

STORE = "data/ds/processed/working/a.zarr"
RAW = "data/ds/raw/counts.h5ad"
LABELS = "analysis/ds/topic/agent_annot_v1/outputs/labels.parquet"
FIGURE = "analysis/ds/topic/human_fig_v1/outputs/fig.parquet"


def declare(task, inputs):
    """What the `declare-inputs` skill leaves: the id, then the list."""
    task_id(task)
    text = (task / "inputs.yaml").read_text()
    (task / "inputs.yaml").write_text(text + yaml.safe_dump({"inputs": inputs}))


@pytest.fixture
def project(repo):
    """Three tasks in the main checkout: one builds a store, one adds a key and a file, one makes a figure."""
    main, _ = repo
    topic = main / "analysis" / "ds" / "topic"
    tasks = {name: topic / name for name in ("agent_build_v1", "agent_annot_v1", "human_fig_v1")}
    for task in tasks.values():
        task.mkdir(parents=True)
        (task / "README.md").write_text(f"# {task.name}\n")
    store = main / STORE
    store.parent.mkdir(parents=True)
    (main / RAW).parent.mkdir(parents=True)
    (main / RAW).write_text("raw")

    adata = ad.AnnData(np.ones((6, 2), dtype="float32"), obs=pd.DataFrame({"a": range(6)}, index=list("abcdef")))
    with writes(store, task=tasks["agent_build_v1"]):
        adata.write_zarr(store, consolidate_metadata=False)
    declare(tasks["agent_build_v1"], [{"path": RAW}])

    adata.obs["annot"] = "x"
    with writes(store, task=tasks["agent_annot_v1"]):
        commit_adata(adata, store, keys={"obs": ["annot"]}, yes=True)
    (main / LABELS).parent.mkdir()
    (main / LABELS).write_text("labels")
    declare(tasks["agent_annot_v1"], [{"path": STORE, "keys": ["X", "obs/a"]}])

    (main / FIGURE).parent.mkdir()
    (main / FIGURE).write_text("figure")
    declare(tasks["human_fig_v1"], [{"path": STORE, "keys": ["obs/annot"]}, {"path": LABELS}])
    return main, tasks


def names(found):
    return [task.rsplit("/", 1)[1] for task in found.tasks()]


def test_a_file_traces_back_to_the_raw_data(project):
    main, _ = project
    found = trace(main / FIGURE, start=main)
    assert names(found) == ["agent_annot_v1", "agent_build_v1", "human_fig_v1"]
    assert found.undeclared == []
    assert found.nodes[RAW]["status"] == "source"
    assert {(Path_name(e["source"]), Path_name(e["target"]), e["task"].rsplit("/", 1)[1]) for e in found.edges} >= {
        ("labels.parquet", "fig.parquet", "human_fig_v1"),
        ("counts.h5ad", "a.zarr", "agent_build_v1"),
    }
    tree = found.as_tree().splitlines()
    assert tree[0] == "human_fig_v1/outputs/fig.parquet  [human_fig_v1]"
    assert any(line.strip() == "a.zarr: obs/annot  [agent_annot_v1]" for line in tree)
    assert "-->|agent_annot_v1|" in found.as_mermaid()


def Path_name(node_id):
    return node_id.split("@")[0].split("#")[0].rsplit("/", 1)[1]


def test_a_key_traces_to_the_block_that_wrote_it(project):
    main, _ = project
    found = trace(main / STORE, "obs/annot", start=main)
    target = found.nodes[found.target]
    assert target["keys"] == ["obs/annot"] and target["task"].endswith("agent_annot_v1")
    assert names(found) == ["agent_annot_v1", "agent_build_v1"]
    # both of its inputs came from the build's one write-back: one node, labelled with the keys reached
    (build,) = [n for n in found.nodes.values() if (n.get("task") or "").endswith("agent_build_v1")]
    assert build["keys"] == ["X", "obs/a"] and build["written"] == 2


def test_a_task_without_declared_inputs_stops_the_trace(project, monkeypatch):
    main, tasks = project
    file = tasks["agent_annot_v1"] / "inputs.yaml"
    file.write_text(file.read_text().split("inputs:")[0])
    assert declared(tasks["agent_annot_v1"]) is None
    assert trace(main / FIGURE, start=main).undeclared == ["analysis/ds/topic/agent_annot_v1"]

    monkeypatch.chdir(main)
    result = CliRunner().invoke(app, ["trace", FIGURE])
    assert result.exit_code == 1 and "analysis/ds/topic/agent_annot_v1" in result.output


def test_a_file_in_the_home_directory_is_a_source(project, monkeypatch, tmp_path):
    main, tasks = project
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "model.pkl").write_text("model")
    file = tasks["agent_build_v1"] / "inputs.yaml"
    file.write_text(file.read_text().split("inputs:")[0])
    declare(tasks["agent_build_v1"], [{"path": RAW}, {"path": "~/model.pkl"}])
    found = trace(main / STORE, "X", start=main)
    assert found.nodes[str(tmp_path / "model.pkl")]["status"] == "source"
    assert missing_inputs(tasks["agent_build_v1"]) == []


def test_an_empty_list_is_declared(project):
    main, tasks = project
    file = tasks["agent_build_v1"] / "inputs.yaml"
    file.write_text(file.read_text().split("inputs:")[0] + "inputs: []\n")
    found = trace(main / STORE, "X", start=main)
    assert found.undeclared == [] and names(found) == ["agent_build_v1"]


def test_a_whole_store_and_a_dated_copy(project):
    """A copy's keys keep their writers; a task that used the whole store rests on every write-back to it."""
    main, tasks = project
    mint = main / "analysis" / "ds" / "topic" / "human_mint_v1"
    mint.mkdir()
    copy = main / "data" / "ds" / "processed" / "working" / "b.zarr"
    with writes(copy, task=mint):
        shutil.copytree(main / STORE, copy)
    declare(mint, [{"path": STORE, "keys": ["*"]}])

    found = trace(copy, "obs/annot", start=main)
    assert found.nodes[found.target]["task"].endswith("agent_annot_v1")  # the record travelled with the copy

    declare_again = tasks["human_fig_v1"] / "inputs.yaml"
    declare_again.write_text(declare_again.read_text().split("inputs:")[0])
    declare(tasks["human_fig_v1"], [{"path": STORE, "keys": ["*"]}])
    whole = trace(main / FIGURE, start=main)
    assert sum(e["target"] == whole.target for e in whole.edges) == 2  # the build's write-back and the annotation's


def test_a_whole_store_means_its_write_backs_up_to_then(project):
    """What was written to the store after a file was made from it cannot have gone into the file."""
    main, tasks = project
    file = tasks["human_fig_v1"] / "inputs.yaml"
    file.write_text(file.read_text().split("inputs:")[0])
    declare(tasks["human_fig_v1"], [{"path": STORE, "keys": ["*"]}])

    def write_backs_behind_the_figure(age):
        os.utime(main / FIGURE, (time.time() - age,) * 2)
        found = trace(main / FIGURE, start=main)
        return sum(edge["target"] == found.target and "@" in edge["source"] for edge in found.edges)

    assert write_backs_behind_the_figure(age=-60) == 2  # the figure is newer than both
    assert write_backs_behind_the_figure(age=3600) == 0  # older than both: the store is a leaf with no record


def test_a_key_without_a_record_and_a_task_that_is_gone(project):
    main, tasks = project
    root = __import__("zarr").open_group(str(main / STORE), mode="a")
    ad.io.write_elem(root["obsm"], "X_stray", np.zeros((6, 2)))
    stray = trace(main / STORE, "obsm/X_stray", start=main)
    assert stray.nodes[stray.target]["status"] == "no record" and stray.tasks() == []

    file = tasks["human_fig_v1"] / "inputs.yaml"  # a task that used the whole store rests on that key too
    file.write_text(file.read_text().split("inputs:")[0])
    declare(tasks["human_fig_v1"], [{"path": STORE, "keys": ["*"]}])
    whole = trace(main / FIGURE, start=main)
    assert whole.nodes[f"{STORE}#no record"]["keys"] == ["obsm/X_stray"]
    assert {
        "source": f"{STORE}#no record",
        "target": whole.target,
        "task": str(tasks["human_fig_v1"].relative_to(main)),
    } in whole.edges

    shutil.rmtree(tasks["agent_annot_v1"])
    gone = trace(main / STORE, "obs/annot", start=main)
    status = gone.nodes[gone.target]["status"]
    assert status == "task not in this checkout: analysis/ds/topic/agent_annot_v1 on main"


def test_a_copied_task_directory_is_caught(project):
    main, tasks = project
    shutil.copytree(tasks["agent_annot_v1"], tasks["agent_annot_v1"].with_name("agent_annot_v2"))
    with pytest.raises(ValueError, match="a copied task directory"):
        trace(main / FIGURE, start=main)


def test_an_unmerged_task_is_found_from_its_worktree(project, repo):
    main, worktree = repo
    task = worktree / "analysis" / "ds" / "topic" / "agent_late_v1"
    task.mkdir(parents=True)
    adata = ad.AnnData(obs=pd.DataFrame({"late": 1}, index=list("abcdef")))
    with writes(main / STORE, task=task):
        commit_adata(adata, main / STORE, keys={"obs": ["late"]}, yes=True)
    declare(task, [{"path": STORE, "keys": ["obs/annot"]}])

    from_worktree = trace(main / STORE, "obs/late", start=worktree)
    assert names(from_worktree) == ["agent_annot_v1", "agent_build_v1", "agent_late_v1"]
    from_main = trace(main / STORE, "obs/late", start=main)
    assert from_main.nodes[from_main.target]["status"].endswith("agent_late_v1 on wt")


def test_trace_command_formats(project, monkeypatch):
    main, _ = project
    monkeypatch.chdir(main)
    tasks = CliRunner().invoke(app, ["trace", FIGURE, "--format", "tasks"])
    assert tasks.exit_code == 0, tasks.output
    assert tasks.output.split() == [
        f"analysis/ds/topic/{n}" for n in ("agent_annot_v1", "agent_build_v1", "human_fig_v1")
    ]
    assert CliRunner().invoke(app, ["trace", STORE, "obs/annot", "--format", "mermaid"]).output.startswith("flowchart")
    assert '"target"' in CliRunner().invoke(app, ["trace", STORE, "obs/annot", "--format", "json"]).output
    assert CliRunner().invoke(app, ["trace", FIGURE, "--format", "pdf"]).exit_code == 1


def test_code_committed_after_the_declaration_is_noticed(project, git):
    """By commit history, not by time: the two commits here fall within the same second."""
    main, tasks = project
    commit = ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m")
    git("add", "-A", cwd=main)
    git(*commit, "tasks", cwd=main)
    build = tasks["agent_build_v1"]
    assert not changed_since_declared(build)

    (build / "scripts").mkdir()
    (build / "scripts" / "02_more.py").write_text("x = 1\n")
    git("add", "-A", cwd=main)
    git(*commit, "more code", cwd=main)
    assert changed_since_declared(build)

    declare_file = build / "inputs.yaml"  # declared again, committed with or after the code
    declare_file.write_text(declare_file.read_text() + "# again\n")
    assert not changed_since_declared(build)
    git("add", "-A", cwd=main)
    git(*commit, "declared again", cwd=main)
    assert not changed_since_declared(build)


def test_check_inputs(project, git, monkeypatch):
    main, tasks = project
    monkeypatch.chdir(main)
    git("add", "-A", cwd=main)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "tasks", cwd=main)
    assert "Clean." in CliRunner().invoke(app, ["check", "inputs", *map(str, tasks.values())]).output

    fig = tasks["human_fig_v1"]
    declare_file = fig / "inputs.yaml"
    declare_file.write_text(declare_file.read_text().replace("obs/annot", "obs/typo"))
    assert missing_inputs(fig) == [f"{STORE}: obs/typo"]

    annot = tasks["agent_annot_v1"]
    (annot / "scripts").mkdir()
    (annot / "scripts" / "01_new.py").write_text("x = 1\n")
    assert changed_since_declared(annot) and not changed_since_declared(tasks["agent_build_v1"])

    demo = main / "analysis" / "topic" / "demo_v1"  # the fixture's task: a README, no inputs.yaml
    report = CliRunner().invoke(app, ["check", "inputs"]).output
    assert str(demo) in report and "obs/typo" in report and str(annot) in report
    assert "3 item(s)" in report
    only = CliRunner().invoke(app, ["check", "inputs", str(tasks["agent_build_v1"])]).output
    assert "Clean." in only and os.sep not in only.split("Clean.")[0].replace("[", "")
