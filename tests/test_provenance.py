"""A `writes` block records, in the store, which task wrote which keys.

Some of these pin behaviour of anndata, zarr and SpatialData that the records rely on: a child added under
``uns`` is read back and survives a copy, and a SpatialData store's root attributes are read through its
consolidated metadata.
"""

import json
import shutil
import subprocess
import sys

import anndata as ad
import numpy as np
import pandas as pd
import pytest
import zarr
from typer.testing import CliRunner

from analysis_workflow import commit_adata, writes
from analysis_workflow.cli import app
from analysis_workflow.paths import task_id
from analysis_workflow.provenance import keys, records, uncovered


@pytest.fixture
def adata():
    n = 20
    a = ad.AnnData(
        X=np.ones((n, 4), dtype="float32"),
        obs=pd.DataFrame({"a": np.arange(n)}, index=[f"c{i}" for i in range(n)]),
    )
    a.obsm["X_pca"] = np.zeros((n, 2))
    return a


@pytest.fixture
def task(repo):
    """A task directory in the worktree, so the record's branch is the worktree's."""
    return repo[1] / "analysis" / "topic" / "demo_v1"


@pytest.fixture
def other(repo):
    path = repo[1] / "analysis" / "topic" / "other_v1"
    path.mkdir()
    (path / "README.md").write_text("# other_v1\n\n**Id:** 9f8e7d6c\n")
    return path


@pytest.fixture
def store(tmp_path, adata, task):
    path = tmp_path / "work.zarr"
    with writes(path, task=task):
        adata.write_zarr(path, consolidate_metadata=False)
    return path


def spatial_store(path, adata):
    """The zarr layout of a SpatialData store, without the package: a shapes element and a table."""
    root = zarr.open_group(str(path), mode="w")
    root.attrs["spatialdata_attrs"] = {"version": "0.2"}
    root.create_group("shapes").create_group("cells")
    root.create_group("tables")
    adata.write_zarr(path / "tables" / "table", consolidate_metadata=False)
    zarr.consolidate_metadata(str(path))


@pytest.mark.parametrize("zarr_format", [2, 3])
def test_a_new_object_is_credited_to_the_task(tmp_path, adata, task, zarr_format):
    path = tmp_path / "new.zarr"
    with ad.settings.override(zarr_write_format=zarr_format), writes(path, task=task):
        adata.write_zarr(path, consolidate_metadata=False)

    (record,) = records(path)
    assert record["keys"] == ["X", "obs/a", "obsm/X_pca"]  # an unset `raw` is not a key
    assert record["task"] == task_id(task)
    assert (record["path"], record["branch"]) == ("analysis/topic/demo_v1", "wt")
    (in_memory,) = ad.read_zarr(path).uns["provenance"].values()
    assert json.loads(in_memory) == record


def test_commit_adata_is_recorded_with_its_keys(store, adata, other):
    adata.obs["leiden"] = "x"
    adata.obsm["X_umap"] = np.zeros((adata.n_obs, 2))
    with writes(store, task=other):
        commit_adata(adata, store, keys={"obs": ["leiden"], "obsm": ["X_umap"]}, yes=True)

    first, second = records(store)
    assert second["keys"] == ["obs/leiden", "obsm/X_umap"] and second["path"] == "analysis/topic/other_v1"
    assert first["task"] != second["task"]
    assert uncovered(store) == []
    assert list(ad.read_zarr(store).obs["a"]) == list(adata.obs["a"])  # the obs rewrite left the rest alone


def test_commit_adata_writes_only_inside_a_block(store, adata, task):
    adata.obs["leiden"] = "x"
    assert commit_adata(adata, store, keys={"obs": ["leiden"]}) == {"obs": ["leiden"]}  # the dry run needs none
    with pytest.raises(RuntimeError, match="Not inside a `writes` block"):
        commit_adata(adata, store, keys={"obs": ["leiden"]}, yes=True)
    with writes(store.parent / "another.zarr", task=task), pytest.raises(RuntimeError, match="writes"):
        commit_adata(adata, store, keys={"obs": ["leiden"]}, yes=True)  # a block for another store
    assert "obs/leiden" not in keys(store)


def test_the_records_key_is_reserved(store, adata, task):
    adata.uns["provenance"] = {"mine": 1}
    with pytest.raises(ValueError, match="records of who wrote what"):
        commit_adata(adata, store, keys={"uns": ["provenance"]})

    adata.uns["note"] = {"a": 1}  # the check must not use up keys given as an iterator
    with writes(store, task=task):
        assert commit_adata(adata, store, keys={"uns": iter(["note"])}, yes=True) == {"uns": ["note"]}
    assert "uns/note" in keys(store)


@pytest.mark.parametrize("where", ["script", "notebook"])
def test_the_task_is_the_one_the_code_runs_in(tmp_path, task, where):
    """A script is credited to its own task directory; a notebook kernel to its working directory."""
    path = tmp_path / "new.zarr"
    code = (
        "import sys, anndata as ad, numpy as np\n"
        "from analysis_workflow import writes\n"
        "with writes(sys.argv[1]):\n"
        "    ad.AnnData(np.ones((3, 2), dtype='float32')).write_zarr(sys.argv[1], consolidate_metadata=False)\n"
    )
    (task / "scripts").mkdir()
    (task / "notebooks").mkdir()
    if where == "script":
        (task / "scripts" / "01_write.py").write_text(code)
        command, cwd = [sys.executable, str(task / "scripts" / "01_write.py"), str(path)], tmp_path
    else:
        command, cwd = [sys.executable, "-c", code, str(path)], task / "notebooks"
    subprocess.run(command, cwd=cwd, check=True, capture_output=True)
    assert records(path)[0]["path"] == "analysis/topic/demo_v1"


def test_outside_a_task_it_needs_one(tmp_path, adata, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="pass `task="), writes(tmp_path / "new.zarr"):
        pass


def test_a_copy_keeps_each_key_with_its_writer(tmp_path, store, other):
    copy = tmp_path / "copy.zarr"
    with writes(copy, task=other):
        shutil.copytree(store, copy)
    assert [r["path"] for r in records(copy)] == ["analysis/topic/demo_v1"]

    dated = tmp_path / "dated.zarr"
    adata = ad.read_zarr(store)
    del adata.obsm["X_pca"]
    adata.obs["fixed"] = 1
    with writes(dated, task=other):
        adata.write_zarr(dated, consolidate_metadata=False)
    old, new = records(dated)
    assert old["path"] == "analysis/topic/demo_v1" and new["path"] == "analysis/topic/other_v1"
    assert new["keys"] == ["obs/fixed"]
    assert uncovered(dated) == []


def test_a_key_that_is_gone_fails_the_block(store, task):
    with pytest.raises(ValueError, match="No longer in .*obsm/X_pca.*only grow"), writes(store, task=task):
        shutil.rmtree(store / "obsm" / "X_pca")


def test_a_store_that_is_gone_fails_the_block(store, task):
    with pytest.raises(ValueError, match="was a store before the block"), writes(store, task=task):
        shutil.rmtree(store)


def test_a_failing_body_keeps_its_error_and_its_record(store, adata, task):
    adata.obsm["X_new"] = np.zeros((adata.n_obs, 2))
    with pytest.raises(OSError, match="later line"), writes(store, task=task):
        commit_adata(adata, store, keys={"obsm": ["X_new"]}, yes=True)
        raise OSError("a later line fails")
    assert records(store)[-1]["keys"] == ["obsm/X_new"]


def test_a_consolidated_anndata_store_is_refused(tmp_path, adata, task):
    existing = tmp_path / "cons.zarr"
    adata.write_zarr(existing, consolidate_metadata=True)
    with pytest.raises(ValueError, match="consolidated metadata"), writes(existing, task=task):
        pass

    new = tmp_path / "new.zarr"
    with pytest.raises(ValueError, match="consolidated metadata"), writes(new, task=task):
        adata.write_zarr(new, consolidate_metadata=True)


def test_records_survive_copies_of_the_object(tmp_path, store):
    adata = ad.read_zarr(store)
    adata.write_h5ad(tmp_path / "copy.h5ad")
    adata[:5].copy().write_zarr(tmp_path / "subset.zarr", consolidate_metadata=False)
    assert len(ad.read_h5ad(tmp_path / "copy.h5ad").uns["provenance"]) == 1
    assert [r["path"] for r in records(tmp_path / "subset.zarr")] == ["analysis/topic/demo_v1"]


def test_a_plain_file_gets_no_record(tmp_path, task):
    path = tmp_path / "registry.csv"
    with writes(path, task=task):
        path.write_text("a,b\n1,2\n")
    assert path.read_text() == "a,b\n1,2\n" and records(path) == []


def test_spatialdata_layout(tmp_path, adata, task, other):
    """Elements and table keys are recorded in the root attributes, where the consolidated metadata shows them."""
    path = tmp_path / "section.zarr"
    with writes(path, task=task):
        spatial_store(path, adata)
    assert records(path)[0]["keys"] == [
        "shapes/cells",
        "tables/table",
        "tables/table/X",
        "tables/table/obs/a",
        "tables/table/obsm/X_pca",
    ]

    with writes(path, task=other):
        zarr.open_group(str(path), mode="a", use_consolidated=False)["shapes"].create_group("nuclei")
    assert records(path)[1]["keys"] == ["shapes/nuclei"] and uncovered(path) == []
    through_consolidated = zarr.open_group(str(path), mode="r")
    assert through_consolidated.metadata.consolidated_metadata is not None
    assert len(through_consolidated.attrs["provenance"]) == 2


def test_spatialdata_reads_and_carries_the_records(tmp_path, adata, task, other):
    sd = pytest.importorskip("spatialdata")
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Point
    from spatialdata.models import ShapesModel, TableModel

    def shapes():
        return ShapesModel.parse(gpd.GeoDataFrame({"radius": [1.0, 1.0]}, geometry=[Point(0, 0), Point(1, 1)]))

    path = tmp_path / "section.zarr"
    with writes(path, task=task):
        sd.SpatialData(shapes={"cells": shapes()}, tables={"table": TableModel.parse(adata)}).write(path)
    stale = sd.read_zarr(path)

    sdata = sd.read_zarr(path)
    sdata["nuclei"] = shapes()
    with writes(path, task=other):
        sdata.write_element("nuclei")
    stale["cells2"] = shapes()
    with writes(path, task=task):
        stale.write_element("cells2")  # an object read before the last record was written

    assert [r["keys"] for r in records(path)][1:] == [["shapes/nuclei"], ["shapes/cells2"]]
    assert len(sd.read_zarr(path).attrs["provenance"]) == 3

    copy = tmp_path / "copy.zarr"
    with writes(copy, task=other):
        sd.read_zarr(path).write(copy)
    assert len(records(copy)) == 3 and uncovered(copy) == []


def test_the_cell_magic(tmp_path, adata, task):
    pytest.importorskip("IPython")
    from IPython.core.interactiveshell import InteractiveShell

    from analysis_workflow import register_magic

    shell = InteractiveShell.instance()
    register_magic()
    path = tmp_path / "new.zarr"
    shell.user_ns.update(adata=adata, PATH=path, TASK=task)

    result = shell.run_cell("%%writes PATH --task TASK\nadata.write_zarr(PATH, consolidate_metadata=False)")
    assert result.success, result.error_in_exec
    assert records(path)[0]["path"] == "analysis/topic/demo_v1"

    assert not shell.run_cell("%%writes PATH --task TASK\n1 / 0").success


def test_check_provenance(store):
    clean = CliRunner().invoke(app, ["check", "provenance", str(store)])
    assert clean.exit_code == 0 and "Clean." in clean.output, clean.output

    root = zarr.open_group(str(store), mode="a")
    ad.io.write_elem(root["obsm"], "X_stray", np.zeros((20, 2)))  # written outside a block
    stray = CliRunner().invoke(app, ["check", "provenance", str(store)])
    assert "obsm/X_stray" in stray.output and "1 item(s) to look at." in stray.output


def test_a_task_without_an_id_cannot_write(tmp_path, adata, task):
    """The id is in the README's header, from `analysis-workflow new`; without one nothing is written."""
    assert task_id(task) == "0a1b2c3d"
    (task / "README.md").write_text("# demo_v1\n")
    path = tmp_path / "new.zarr"
    with pytest.raises(ValueError, match=r"no `\*\*Id:\*\*` line"), writes(path, task=task):
        adata.write_zarr(path, consolidate_metadata=False)
    assert task_id(task) is None and not path.exists()
