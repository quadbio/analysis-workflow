"""Which task wrote which keys of a shared store, recorded inside the store by the block that wrote them.

``with writes(path):`` lists the store's keys before and after its body and credits what appeared to the task the
code runs in. The record lives with the data: in an AnnData store as one child of ``uns/provenance`` per block, in a
SpatialData store as one entry of the root attribute ``provenance``; readers see it as ``adata.uns["provenance"]``
and ``sdata.attrs["provenance"]``. A copy of a store carries its records, and a block credits only keys that none
of them covers, so copying an object keeps each key with the task that made it. The block that writes a copy
drops from those records the keys the copy did not keep.

A store older than its records gets them from `credit`, which adds the record a block would have written for keys
that are already there.

The stores are read as zarr groups, in format 2 or 3, so SpatialData is not imported. In an existing store only
children are ever added under ``uns/provenance``: rewriting that group's metadata would replace the file another
node is reading.
"""

import datetime
import json
import logging
import subprocess
from contextlib import contextmanager
from pathlib import Path

import zarr
from anndata.io import read_elem, write_elem
from zarr.errors import ContainsGroupError

from analysis_workflow.paths import TaskPaths, _checkouts_of, current_task, task_id, task_paths
from analysis_workflow.working import CONSOLIDATED, keys_on_disk

logger = logging.getLogger(__name__)

#: Where the records are: ``uns[KEY]`` in an AnnData store, ``attrs[KEY]`` at a SpatialData store's root.
KEY = "provenance"

#: How a record's ``at`` is written, in UTC; such strings order as their times do.
TIME = "%Y-%m-%dT%H:%M:%S.%fZ"

#: The element kinds of a SpatialData store.
ELEMENT_KINDS = ("images", "labels", "points", "shapes", "tables")

#: Stores with a block open in this process; `commit_adata` writes to no other.
_open: set[Path] = set()


def _root(path, mode="r"):
    # A SpatialData store's consolidated metadata lags behind elements added since it was written.
    return zarr.open_group(str(path), mode=mode, use_consolidated=False)


def _present(group, name) -> bool:
    """Whether ``name`` holds something: anndata writes an unset ``raw`` or ``X`` as a null element."""
    return name in group and group[name].attrs.get("encoding-type") != "null"


def _anndata_keys(path, prefix="") -> set[str]:
    found = {f"{prefix}{slot}/{k}" for slot, ks in keys_on_disk(path).items() for k in ks if (slot, k) != ("uns", KEY)}
    root = _root(path)
    return found | {prefix + name for name in ("X", "raw") if _present(root, name)}


def _kind(path) -> str | None:
    """``"anndata"`` or ``"spatialdata"`` for a store this module can record in; None for anything else."""
    path = Path(path)
    if not any((path / metadata).is_file() for metadata in ("zarr.json", ".zgroup")):
        return None
    attrs = _root(path).attrs
    if "spatialdata_attrs" in attrs:
        return "spatialdata"
    return "anndata" if attrs.get("encoding-type") == "anndata" else None


def keys(path) -> set[str]:
    """The keys of the store at ``path``, read from its metadata; empty for anything that is not a store.

    AnnData: ``<slot>/<key>``, ``X`` and ``raw``. SpatialData: ``<kind>/<element>``, and each table's keys as
    ``tables/<name>/<slot>/<key>``.
    """
    kind = _kind(path)
    if kind == "anndata":
        return _anndata_keys(path)
    if kind != "spatialdata":
        return set()
    root, found = _root(path), set()
    for element_kind in ELEMENT_KINDS:
        for name in root[element_kind] if element_kind in root else ():
            found.add(f"{element_kind}/{name}")
            if element_kind == "tables":
                found |= _anndata_keys(Path(path) / "tables" / name, f"tables/{name}/")
    return found


def _named(path) -> dict[str, dict]:
    """The store's records, by the name each is kept under."""
    kind = _kind(path)
    if kind == "spatialdata":
        return dict(_root(path).attrs.get(KEY, {}))
    root = _root(path) if kind == "anndata" else {}
    if "uns" in root and KEY in root["uns"]:
        return {name: json.loads(read_elem(root["uns"][KEY][name])) for name in root["uns"][KEY]}
    return {}


def records(path) -> list[dict]:
    """The records in the store at ``path``, oldest first: ``{"task", "path", "branch", "keys", "at"}`` each.

    One added by `credit` also holds ``recorded``, when it was added.
    """
    return sorted(_named(path).values(), key=lambda record: record["at"])


def _prune(path, present: set[str]) -> None:
    """In a new copy, drop from the records it carries the keys it did not keep, and the records left with none."""
    named = _named(path)
    kept = {name: {**record, "keys": [k for k in record["keys"] if k in present]} for name, record in named.items()}
    if kept == named:
        return
    root = _root(path, mode="a")
    if _kind(path) == "spatialdata":
        root.attrs[KEY] = {name: record for name, record in kept.items() if record["keys"]}
        zarr.consolidate_metadata(str(path))
        return
    group = root["uns"][KEY]
    for name, record in kept.items():
        if not record["keys"]:
            del group[name]
        elif record != named[name]:
            write_elem(group, name, json.dumps(record))


def uncovered(path) -> list[str]:
    """The keys of the store at ``path`` that no record covers."""
    return sorted(keys(path) - {k for record in records(path) for k in record["keys"]})


def _write(path, record: dict) -> None:
    name = record["at"].translate({ord(c): None for c in "-:."}) + "_" + record["task"]
    root = _root(path, mode="a")
    if _kind(path) == "spatialdata":
        root.attrs[KEY] = {**root.attrs.get(KEY, {}), name: record}
        zarr.consolidate_metadata(str(path))  # SpatialData reads a store through its consolidated metadata
        return
    uns = root["uns"]
    try:
        group = uns[KEY]
    except KeyError:
        try:
            group = uns.create_group(KEY, attributes={"encoding-type": "dict", "encoding-version": "0.1.0"})
        except ContainsGroupError:  # another writer made it meanwhile
            group = uns[KEY]
    write_elem(group, name, json.dumps(record))


def _task(task) -> TaskPaths:
    if isinstance(task, TaskPaths):
        return task
    try:
        return current_task() if task is None else task_paths(Path(task) / "README.md")
    except (ValueError, RuntimeError) as err:
        raise ValueError(
            "`writes` credits what it records to a task: run it from a task directory, or pass `task=<its directory>`."
        ) from err


def _consolidated(path) -> bool:
    """Whether ``path`` is an AnnData store with consolidated metadata, where an added record stays invisible."""
    return _kind(path) == "anndata" and zarr.open_group(str(path), mode="r").metadata.consolidated_metadata is not None


def _record(path: Path, before: set[str], task: TaskPaths, identity: str) -> str | None:
    """Record what appeared in the store since ``before``; return what broke a rule, if anything did."""
    if _kind(path) is None:
        if before:
            return f"{path} was a store before the block and is none now. Shared stores only grow."
        if path.exists():
            logger.info("%s is not an AnnData or SpatialData store: no record.", path)
        return None
    if _consolidated(path):
        return CONSOLIDATED.format(path=path)
    after = keys(path)
    if not before:  # a store this block created: if it is a copy, its records name what the original held
        _prune(path, after)
    covered = {k for record in records(path) for k in record["keys"]}
    if added := sorted(after - before - covered):
        checkout, _ = _checkouts_of(task.task)
        branch = subprocess.run(
            ["git", "-C", str(checkout), "branch", "--show-current"], capture_output=True, text=True
        ).stdout.strip()
        record = {
            "task": identity,
            "path": task.task.relative_to(checkout).as_posix(),
            "branch": branch or None,
            "keys": added,
            "at": datetime.datetime.now(datetime.UTC).strftime(TIME),
        }
        _write(path, record)
        logger.info("Recorded %d key(s) of %s for %s.", len(added), path.name, record["path"])
    if gone := sorted(before - after):
        return (
            f"No longer in {path}: {', '.join(gone)}. Shared stores only grow; removing or renaming a key means "
            "a new dated copy."
        )
    return None


@contextmanager
def writes(path, *, task: TaskPaths | str | Path | None = None):
    """Record what the body adds to the store at ``path``; every write into shared storage sits in one.

    Parameters
    ----------
    path
        The store on disk, an AnnData or SpatialData zarr store, existing or about to be created. Anything else
        (a plain file) is left without a record.
    task
        The task to credit, as its directory, when that is not the one the code runs in.

    Raises
    ------
    ValueError
        If the code runs in no task directory and ``task`` is not given, or the task's README has no id; if a
        key that was in the store is gone
        after the body, since shared stores only grow; or for an AnnData store with consolidated metadata, in
        which a record would be invisible to readers.
    """
    path = Path(path).resolve()
    credited = _task(task)
    if (identity := task_id(credited.task)) is None:
        raise ValueError(
            f"{credited.task / 'README.md'} has no `**Id:**` line, under which the store would record the write. "
            "`analysis-workflow new` gives a task one."
        )
    if _consolidated(path):
        raise ValueError(CONSOLIDATED.format(path=path))
    before = keys(path)
    _open.add(path)
    try:
        yield
    finally:  # what the body did write is recorded even when it failed part-way
        _open.discard(path)
        problem = _record(path, before, credited, identity)
    if problem:
        raise ValueError(problem)


def credit(path, keys, *, task: TaskPaths | str | Path, at: datetime.datetime, yes: bool = False) -> list[str]:
    """Credit ``keys`` that are already in the store at ``path`` to the task that wrote them.

    For a store older than its records, in a repo that adopts these conventions: a `writes` block records only
    what appears while it is open. Dry run by default: with ``yes=False`` the record is logged and nothing is
    written.

    Parameters
    ----------
    keys
        The keys to credit, named as the store's records name them: ``obs/leiden``, ``X``, ``shapes/cells``.
    task
        The directory of the task that wrote them.
    at
        When it wrote them; without a time zone, in UTC. A trace of a whole store follows only the records
        older than what was made from it.

    Returns
    -------
    The keys credited (or that would be credited).

    Raises
    ------
    KeyError
        If a key is not in the store, or a record already covers it.
    ValueError
        If the task's README has no id, ``at`` is in the future, the store already holds a record of this task
        at ``at``, ``path`` is no store, or it is an AnnData store with consolidated metadata.
    """
    path, credited, wanted = Path(path).resolve(), _task(task), sorted(set(keys))
    if (identity := task_id(credited.task)) is None:
        raise ValueError(f"{credited.task / 'README.md'} has no `**Id:**` line to record the keys under.")
    if _kind(path) is None:
        raise ValueError(f"{path} is not an AnnData or SpatialData store: it can hold no record.")
    if _consolidated(path):
        raise ValueError(CONSOLIDATED.format(path=path))
    at = at.replace(tzinfo=datetime.UTC) if at.tzinfo is None else at.astimezone(datetime.UTC)
    now = datetime.datetime.now(datetime.UTC)
    if at > now:
        raise ValueError(f"{at.isoformat()} is in the future: `at` is when the task wrote the keys.")
    found, bare = records(path), set(uncovered(path))
    if covered := sorted({k for record in found for k in record["keys"]} & set(wanted)):
        raise KeyError(f"A record of {path} already covers: {', '.join(covered)}.")
    if absent := [k for k in wanted if k not in bare]:
        raise KeyError(f"Not in {path}: {', '.join(absent)}.")
    checkout, _ = _checkouts_of(credited.task)
    record = {
        "task": identity,
        "path": credited.task.relative_to(checkout).as_posix(),
        "branch": None,
        "keys": wanted,
        "at": at.strftime(TIME),
        "recorded": now.strftime(TIME),
    }
    if any((r["task"], r["at"]) == (record["task"], record["at"]) for r in found):
        raise ValueError(f"{path} already holds a record of {record['path']} at {record['at']}.")
    listed = "\n".join(f"  {k}" for k in wanted) or "  nothing to credit"
    logger.info("Crediting to %s, as written %s, in %s:\n%s", record["path"], record["at"], path, listed)
    if not yes or not wanted:
        if not yes:
            logger.info("Dry run (yes=False): %s unchanged. Re-run with yes=True to write.", path)
        return wanted
    _write(path, record)
    return wanted


def is_open(path) -> bool:
    """Whether a `writes` block for the store at ``path`` is open in this process."""
    return Path(path).resolve() in _open


def register_magic() -> None:
    """In IPython, make ``%%writes <path> [--task <directory>]`` run a cell inside a `writes` block."""
    try:
        from IPython import get_ipython
    except ImportError:
        return
    if (shell := get_ipython()) is None:
        return

    def magic(line, cell):
        path, _, task = line.partition("--task")
        with writes(shell.ev(path), task=shell.ev(task) if task.strip() else None):
            result = shell.run_cell(cell)
            if error := result.error_before_exec or result.error_in_exec:
                raise error

    shell.register_magic_function(magic, magic_kind="cell", magic_name="writes")
