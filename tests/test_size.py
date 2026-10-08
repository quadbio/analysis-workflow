import logging

import anndata as ad
import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from analysis_workflow import analyze_anndata_size
from analysis_workflow.size import _get_array_size, _safe_get_size


@pytest.fixture
def adata():
    n, m = 50, 20
    a = ad.AnnData(
        X=np.random.default_rng(0).random((n, m)).astype(np.float32),
        obs=pd.DataFrame({"group": ["a", "b"] * (n // 2)}, index=[f"c{i}" for i in range(n)]),
        var=pd.DataFrame(index=[f"g{i}" for i in range(m)]),
    )
    a.layers["counts"] = sp.random(n, m, density=0.2, format="csr", random_state=0)
    return a


def test_numpy_array_in_every_unit():
    arr = np.zeros((100, 50), dtype=np.float64)
    nbytes = 100 * 50 * 8
    for unit, div in (("bytes", 1), ("KB", 1024), ("MB", 1024**2), ("GB", 1024**3)):
        assert _get_array_size(arr, unit) == nbytes / div


@pytest.mark.parametrize("fmt", ["csr", "csc", "coo"])
def test_sparse_is_smaller_than_dense(fmt):
    dense = np.eye(100, dtype=np.float32)
    size = _get_array_size(sp.coo_matrix(dense).asformat(fmt), "bytes")
    assert 0 < size < dense.nbytes


def test_sparse_array_counts_too():
    assert _get_array_size(sp.csr_array(np.eye(10)), "bytes") > 0


def test_invalid_unit_and_type():
    with pytest.raises(ValueError, match="Invalid unit"):
        _get_array_size(np.zeros(10), "TB")
    with pytest.raises(TypeError, match="Unsupported type"):
        _get_array_size([1, 2, 3], "bytes")


def test_unmeasurable_values_count_as_zero():
    assert _safe_get_size({"key": "value"}, "bytes") == 0.0


def test_components(adata):
    sizes = analyze_anndata_size(adata, unit="bytes", log_result=False)
    assert set(sizes) == {"X", "obs", "var", "obsm", "varm", "obsp", "varp", "layers", "uns", "raw"}
    assert sizes["X"] == adata.X.nbytes
    assert sizes["layers"] > 0
    assert sizes["obsm"] == sizes["obsp"] == sizes["raw"] == 0.0


def test_raw_is_measured(adata):
    adata.raw = adata.copy()
    assert analyze_anndata_size(adata, unit="bytes", log_result=False)["raw"] > 0


def test_logs_the_total(adata, caplog):
    with caplog.at_level(logging.INFO):
        analyze_anndata_size(adata, unit="MB")
    assert "AnnData memory usage" in caplog.text
