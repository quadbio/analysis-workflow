# Why the storage rules are what they are

**Zarr directory stores.** Each AnnData key is its own node, so adding yours touches nothing else. An `.h5ad` is
rewritten whole, and a zip store cannot take a key in place. Two settings keep a store additive: no consolidated
metadata (keys added later are invisible to readers, so `commit_adata` refuses such a store; write with
`consolidate_metadata=False`), and `anndata.settings.auto_shard_zarr_v3` off. How `commit_adata` writes: its
module docstring.

**Shared objects** (working objects, SpatialData stores, anything other code loads) have no second copy and are
read by several sessions. Additions written onto freshly re-read state commute, so concurrent sessions cannot lose
each other's work; a removal cannot be expressed that way, hence the new dated copy. If the storage keeps
snapshots, check them before declaring anything lost. Everything else is rebuilt by a committed script, so it needs
no write machinery.

**SpatialData stores.** Images, labels, points and shapes usually exist once: add an element under a new name
rather than replacing one. When a table lives in both a store and a working object, the repo's `AGENTS.md` says
which one is the source.
