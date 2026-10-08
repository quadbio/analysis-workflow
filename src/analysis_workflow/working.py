"""Add new keys to a shared AnnData zarr store without touching anyone else's.

Two write paths, because the on-disk encoding has two shapes. Outside ``obs``/``var`` an addition is
a new child node. In ``obs``/``var`` the column set lives in the element's ``column-order`` attribute
and readers return only the columns listed there, so adding one rewrites the dataframe, re-read fresh
to carry forward columns added since. Concurrent mapping additions are safe; concurrent ``obs``/``var``
additions fail loudly (``KeyError``), never silently.
"""

import logging

import zarr
from anndata import AnnData
from anndata.io import read_elem, write_elem

logger = logging.getLogger(__name__)

#: Slots whose additions are independent creates.
MAPPING_SLOTS = ("obsm", "varm", "layers", "obsp", "varp", "uns")

#: Slots stored as a dataframe, where the column set lives in a ``column-order`` attribute.
FRAME_SLOTS = ("obs", "var")

SLOTS = (*FRAME_SLOTS, *MAPPING_SLOTS)


def _in_memory(adata: AnnData) -> dict[str, set[str]]:
    keys = {"obs": set(adata.obs.columns), "var": set(adata.var.columns)}
    for slot in MAPPING_SLOTS:
        # anndata 0.13 lists a ``None`` key in ``layers`` standing for ``X``. It is not a layer.
        keys[slot] = {k for k in getattr(adata, slot) if k is not None}
    return keys


def keys_on_disk(path) -> dict[str, set[str]]:
    """What the store at ``path`` already holds, per slot. Reads metadata only, no data."""
    root = zarr.open_group(str(path), mode="r")
    keys = {}
    for slot in FRAME_SLOTS:
        keys[slot] = set(root[slot].attrs.get("column-order", [])) if slot in root else set()
    for slot in MAPPING_SLOTS:
        keys[slot] = set(root[slot]) if slot in root else set()
    return keys


def _describe(value) -> str:
    shape = getattr(value, "shape", None)
    return f"shape {tuple(shape)}" if shape is not None else type(value).__name__


def commit_adata(adata: AnnData, path, *, yes: bool = False) -> dict[str, list[str]]:
    """Write keys that are in ``adata`` but not yet in the zarr store at ``path``.

    Dry run by default: with ``yes=False`` the additions are logged and nothing is written. Keys
    already on disk are never written, so ``adata`` may hold just the slot you read and your new keys.

    Returns
    -------
    The keys written (or that would be written), per slot.

    Raises
    ------
    ValueError
        If the store has consolidated metadata, which would make the additions invisible to
        readers, or if another session is concurrently rewriting ``obs``/``var``.
    """
    root = zarr.open_group(str(path), mode="a")
    if root.metadata.consolidated_metadata is not None:
        raise ValueError(
            f"{path} has consolidated metadata. Keys added to such a store are silently invisible "
            "to readers, so a working object must not be consolidated. Rewrite it with "
            "adata.write_zarr(..., consolidate_metadata=False)."
        )

    mine, theirs = _in_memory(adata), keys_on_disk(path)
    new = {slot: sorted(mine[slot] - theirs[slot]) for slot in SLOTS}
    new = {slot: keys for slot, keys in new.items() if keys}

    lines = [f"  + {slot}[{k!r}]  {_describe(getattr(adata, slot)[k])}" for slot, ks in new.items() for k in ks]
    logger.info("Committing to %s:\n%s", path, "\n".join(lines) if lines else "  nothing to write")
    if not yes or not new:
        if not yes:
            logger.info("Dry run (yes=False): %s unchanged. Re-run with yes=True to write.", path)
        return new

    for slot, keys in new.items():
        if slot in FRAME_SLOTS:
            # The column set lives in the parent's ``column-order``, so the element is rewritten.
            # Read it fresh first, to carry forward columns another session added since.
            try:
                frame = read_elem(root[slot])
            except KeyError as err:
                raise ValueError(
                    f"Could not read {slot!r} from {path}: another session is most likely "
                    "rewriting it right now. Nothing was written; re-run in a moment."
                ) from err
            for key in keys:
                frame[key] = getattr(adata, slot)[key]
            write_elem(root, slot, frame)
        else:
            for key in keys:
                write_elem(root[slot], key, getattr(adata, slot)[key])

    logger.info("Committed to %s.", path)
    return new
