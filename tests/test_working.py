"""Additive write-back to a working AnnData zarr store.

Several of these pin anndata behaviour that is **not** documented: the reader ignoring columns
absent from ``column-order``, and a key added past consolidated metadata being silently invisible.
`commit_adata` depends on both, so if an anndata upgrade changes them this suite should fail
rather than the data being quietly wrong.
"""

import anndata as ad
import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp
import zarr
from anndata.io import read_elem, write_elem

from analysis_workflow import commit_adata, keys_on_disk


@pytest.fixture
def adata():
    n, m = 60, 8
    a = ad.AnnData(
        X=sp.random(n, m, density=0.3, format="csr", dtype="float32", random_state=0),
        obs=pd.DataFrame({"a": np.arange(n)}, index=[f"c{i}" for i in range(n)]),
        var=pd.DataFrame({"g": np.arange(m)}, index=[f"g{i}" for i in range(m)]),
    )
    a.obsm["X_pca"] = np.random.default_rng(0).random((n, 3))
    a.uns["meta"] = {"k": 1}
    return a


@pytest.fixture
def store(tmp_path, adata):
    path = tmp_path / "work.zarr"
    adata.write_zarr(path, consolidate_metadata=False)
    return path


def test_dry_run_writes_nothing(store, adata):
    adata.obsm["X_new"] = np.zeros((adata.n_obs, 2))
    assert commit_adata(adata, store) == {"obsm": ["X_new"]}
    assert "X_new" not in keys_on_disk(store)["obsm"]


def test_adds_to_mapping_slots(store, adata):
    adata.obsm["X_new"] = np.ones((adata.n_obs, 2))
    adata.obsp["graph"] = sp.eye(adata.n_obs, format="csr")
    adata.uns["note"] = {"hello": "world"}
    commit_adata(adata, store, yes=True)

    back = ad.read_zarr(store)
    assert np.array_equal(back.obsm["X_new"], np.ones((adata.n_obs, 2)))
    assert "graph" in back.obsp
    assert back.uns["note"]["hello"] == "world"
    assert np.allclose(back.obsm["X_pca"], adata.obsm["X_pca"])  # untouched


def test_adds_obs_and_var_columns(store, adata):
    adata.obs["niche_v3"] = pd.Categorical(["x", "y"] * (adata.n_obs // 2))
    adata.var["flag"] = np.arange(adata.n_vars)
    commit_adata(adata, store, yes=True)

    back = ad.read_zarr(store)
    assert "niche_v3" in back.obs.columns
    assert "flag" in back.var.columns
    assert list(back.obs["a"]) == list(adata.obs["a"])  # pre-existing column preserved


def test_existing_keys_are_never_rewritten(store, adata):
    """Another session's key must survive even if ours has the same name and different values."""
    root = zarr.open_group(str(store), mode="a")
    write_elem(root["obsm"], "X_shared", np.full((adata.n_obs, 2), 7.0))

    adata.obsm["X_shared"] = np.zeros((adata.n_obs, 2))
    assert commit_adata(adata, store, yes=True) == {}
    assert np.array_equal(ad.read_zarr(store).obsm["X_shared"], np.full((adata.n_obs, 2), 7.0))


def test_carries_forward_a_concurrent_obs_column(store, adata):
    """Rewriting obs must not drop a column another session added after we read."""
    root = zarr.open_group(str(store), mode="a")
    frame = read_elem(root["obs"])
    frame["theirs"] = np.arange(adata.n_obs)
    write_elem(root, "obs", frame)

    adata.obs["mine"] = np.ones(adata.n_obs)
    commit_adata(adata, store, yes=True)

    cols = ad.read_zarr(store).obs.columns
    assert "mine" in cols and "theirs" in cols


def test_partial_read_then_commit(store, adata):
    """Read one slot, add a key, write it back: the rest of the object is untouched."""
    root = zarr.open_group(str(store), mode="a")
    obs = read_elem(root["obs"])

    partial = ad.AnnData(obs=obs, var=pd.DataFrame(index=adata.var_names))
    partial.obsm["X_derived"] = np.zeros((len(obs), 2))
    commit_adata(partial, store, yes=True)

    back = ad.read_zarr(store)
    assert "X_derived" in back.obsm
    assert back.X.shape == adata.shape  # X was never materialised, let alone rewritten


def test_refuses_a_consolidated_store(tmp_path, adata):
    path = tmp_path / "cons.zarr"
    adata.write_zarr(path, consolidate_metadata=True)
    adata.obsm["X_new"] = np.zeros((adata.n_obs, 2))
    with pytest.raises(ValueError, match="consolidated metadata"):
        commit_adata(adata, path, yes=True)


def test_consolidated_metadata_hides_new_keys(tmp_path, adata):
    """Pins the undocumented behaviour that motivates the refusal above."""
    path = tmp_path / "cons.zarr"
    adata.write_zarr(path, consolidate_metadata=True)

    root = zarr.open_group(str(path), mode="a", use_consolidated=False)
    write_elem(root["obsm"], "X_hidden", np.zeros((adata.n_obs, 2)))

    assert "X_hidden" not in ad.read_zarr(path).obsm  # silently invisible, no error
    assert "X_hidden" in zarr.open_group(str(path), mode="r", use_consolidated=False)["obsm"]


def test_column_order_governs_obs_columns(store, adata):
    """Pins the undocumented behaviour that forces the whole-element rewrite for obs/var."""
    root = zarr.open_group(str(store), mode="a")
    write_elem(root["obs"], "orphan", np.arange(adata.n_obs))

    assert "orphan" not in ad.read_zarr(store).obs.columns
    assert "orphan" not in keys_on_disk(store)["obs"]
