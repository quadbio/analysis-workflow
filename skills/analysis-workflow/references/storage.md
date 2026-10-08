# Working objects and shared stores

The reasons behind the rules in SKILL.md § Data. Read this before writing to any object another session reads.

## Why zarr directory stores

In zarr each AnnData key is its own node, so writing yours never touches anyone else's. An `.h5ad` has to be
rewritten whole, which forces you to read back everyone else's keys and fold them into your copy first. A zarr
**zip** store is a single file, convenient for an immutable snapshot, but it cannot take a new key in place, so it
cannot be a working object.

Two settings keep the store additive:
- **No consolidated metadata.** A key added to a consolidated store is silently invisible to readers.
  `commit_adata` refuses such a store; write it with `adata.write_zarr(path, consolidate_metadata=False)`.
- **No automatic sharding** (`anndata.settings.auto_shard_zarr_v3` stays off). Shards coarsen partial rewrites.

## How `commit_adata` writes

- Mapping slots (`obsm`, `varm`, `layers`, `obsp`, `varp`, `uns`): each addition is a new child node.
  Concurrent additions are safe.
- `obs`/`var`: the column set lives in the element's `column-order` attribute and readers return only the
  columns listed there, so adding one rewrites the dataframe, after re-reading it fresh so that columns another
  session added since are carried forward. Two sessions doing this at once fail loudly (`KeyError`), never
  silently; serialised write-backs, which the sign-off enforces anyway, all survive.

Its module docstring and tests pin the undocumented anndata behaviour this relies on; an anndata upgrade that
changes it fails the tests rather than corrupting data.

## Shared objects versus everything else

The care is for content that has no second copy and that other sessions read: working objects, a SpatialData
store, anything under `processed/` that other code loads.
- Add; never rewrite. New keys written onto freshly re-read state commute, so concurrent sessions cannot lose
  each other's work whatever the order. Removal is not expressible that way: it means a new dated copy, and the
  old one stays so old scripts still run.
- A write needs sign-off on that specific diff.
- If the storage keeps snapshots, check them before declaring anything lost or recomputing anything expensive.

Figures, tables and a task's own objects are written plainly. The task script is the only writer and a rerun
restores them, so temp-file-and-rename machinery buys nothing.

## SpatialData stores

Images, labels, points and shapes usually exist in no second copy, so prefer adding an element under a new name
over replacing one (a re-segmentation is `shapes_v2`, not an overwrite). When a table lives in both a SpatialData
store and a working object, one of them is the source and the other a mirror refreshed only once a result is
final; the repo's `AGENTS.md` says which.

## Size test

A result goes into the working object unless it grows the object materially; `analyze_anndata_size` shows the
per-slot footprint before and after. Otherwise it becomes a standalone minimal AnnData indexed by the same
`obs_names` (in the task's `outputs/`, or promoted to `processed/`). A bare `.npy` loses the index and with it
any safe way to join the result back.
