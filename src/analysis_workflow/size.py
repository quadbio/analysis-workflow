"""How much memory each part of an AnnData takes: the input to the size test for a write-back."""

import logging
from typing import Any, Literal

import numpy as np
import pandas as pd
from anndata import AnnData
from scipy.sparse import issparse

logger = logging.getLogger(__name__)

Unit = Literal["bytes", "KB", "MB", "GB"]

_DIVISORS = {"bytes": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3}


def _get_array_size(array: Any, unit: Unit = "bytes") -> float:
    """Memory size of a NumPy array, SciPy sparse matrix or pandas DataFrame, in ``unit``."""
    if isinstance(array, np.ndarray):
        size_in_bytes = array.nbytes
    elif issparse(array):
        size_in_bytes = sum(
            getattr(array, attr).nbytes for attr in ("data", "indices", "indptr", "row", "col") if hasattr(array, attr)
        )
        if size_in_bytes == 0:
            size_in_bytes = array.nnz * array.dtype.itemsize
    elif isinstance(array, pd.DataFrame):
        size_in_bytes = array.memory_usage(deep=True).sum()
    else:
        raise TypeError(f"Unsupported type: {type(array).__name__}")

    if unit.lower() not in _DIVISORS:
        raise ValueError(f"Invalid unit '{unit}'. Choose from 'bytes', 'KB', 'MB', 'GB'.")
    return size_in_bytes / _DIVISORS[unit.lower()]


def _safe_get_size(obj: Any, unit: Unit) -> float:
    """Like :func:`_get_array_size`, but 0 for anything it cannot measure."""
    if isinstance(obj, np.ndarray | pd.DataFrame) or issparse(obj):
        return _get_array_size(obj, unit)
    return 0.0


def analyze_anndata_size(adata: AnnData, unit: Unit = "GB", *, log_result: bool = True) -> dict[str, float]:
    """Memory footprint of each component of ``adata``.

    Covers ``X``, ``obs``, ``var``, ``obsm``, ``varm``, ``obsp``, ``varp``, ``layers``, ``uns``
    and ``raw``. Dense, sparse and dataframe values are measured; anything else (dask arrays,
    nested ``uns`` dicts) counts as 0.

    Parameters
    ----------
    adata
        AnnData object to analyze.
    unit
        Unit for the returned sizes.
    log_result
        Whether to log the result at INFO level.

    Returns
    -------
    Component name to size in ``unit``.
    """
    sizes: dict[str, float] = {
        "X": _get_array_size(adata.X, unit) if adata.X is not None else 0.0,
        "obs": _get_array_size(adata.obs, unit),
        "var": _get_array_size(adata.var, unit),
    }
    for slot in ("obsm", "varm", "obsp", "varp", "layers", "uns"):
        sizes[slot] = sum(_safe_get_size(value, unit) for value in getattr(adata, slot).values())

    raw = adata.raw
    sizes["raw"] = (
        0.0
        if raw is None
        else (_get_array_size(raw.X, unit) if raw.X is not None else 0.0)
        + _get_array_size(raw.var, unit)
        + sum(_safe_get_size(value, unit) for value in raw.varm.values())
    )

    if log_result:
        logger.info("AnnData memory usage: %.2f %s total", sum(sizes.values()), unit.upper())
        for component, size in sizes.items():
            if size > 0:
                logger.info("  %s: %.2f %s", component, size, unit.upper())
    return sizes
