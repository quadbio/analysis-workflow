"""Trace an artifact back through the tasks that made it.

Two records are followed in turn. A store's own records (`provenance`) say which task wrote a key; a file in a
task's directory belongs to that task by its location. The task's ``inputs.yaml`` then says what its code consumed,
and each of those is traced the same way, down to data that no task made.

The graph has one node per artifact: a file, or the keys one `writes` block added to a store. An edge runs from
an input to what a task made from it, and carries that task.
"""

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from analysis_workflow.paths import (
    ANALYSIS_DIR,
    INPUTS_FILE,
    NON_TASK_DIRS,
    RESERVED_TASK_SUBDIRS,
    UNTRACKED_TASK_DIRS,
    _checkouts_of,
)
from analysis_workflow.provenance import keys, records

TASK_DIR = re.compile(r".+_v\d+")

#: Under `data/<dataset>/`, what arrived from outside the repo: no task made it.
SOURCE_DIRS = frozenset({"raw", "resources"})


def declared(task: Path) -> list[dict] | None:
    """The inputs a task's ``inputs.yaml`` lists; None when it lists none yet (an empty list is a list)."""
    file = task / INPUTS_FILE
    found = (yaml.safe_load(file.read_text()) or {}).get("inputs") if file.exists() else None
    return None if found is None else [dict(entry) for entry in found]


def task_dirs(checkout: Path) -> list[Path]:
    """The task directories of a checkout: those with an ``inputs.yaml``, or named `<name>_vN` with a README."""
    found = []
    for directory, subdirs, files in os.walk(checkout / ANALYSIS_DIR):
        is_task = INPUTS_FILE in files or (TASK_DIR.fullmatch(Path(directory).name) and "README.md" in files)
        if is_task:
            found.append(Path(directory))
        skip = RESERVED_TASK_SUBDIRS if is_task else set(UNTRACKED_TASK_DIRS)
        subdirs[:] = sorted(d for d in subdirs if d not in skip and d not in NON_TASK_DIRS and not d.startswith("."))
    return found


def owner(rel: Path) -> Path | None:
    """The task directory a repo-relative path under `analysis/` is in: the last `<name>_vN` before its contents."""
    if not rel.parts or rel.parts[0] != ANALYSIS_DIR:
        return None
    task = None
    for i, part in enumerate(rel.parts[1:-1], start=1):
        if task is not None and part in RESERVED_TASK_SUBDIRS:
            break
        if TASK_DIR.fullmatch(part):
            task = i
    return None if task is None else Path(*rel.parts[: task + 1])


@dataclass
class Trace:
    """What a trace found. ``nodes`` are artifacts by id; ``edges`` run from an input to what a task made of it."""

    target: str
    nodes: dict[str, dict] = field(default_factory=dict)
    edges: list[dict] = field(default_factory=list)
    undeclared: list[str] = field(default_factory=list)

    def tasks(self) -> list[str]:
        """The task directories on the path, relative to the repo."""
        return sorted({node["task"] for node in self.nodes.values() if node.get("task")})

    def as_json(self) -> str:
        """The whole trace."""
        return json.dumps(asdict(self), indent=2)

    def as_tree(self) -> str:
        """The target first, each artifact's inputs indented below it."""
        lines, seen = [], set()

        def walk(node_id: str, depth: int) -> None:
            node = self.nodes[node_id]
            by = Path(node["task"]).name if node.get("task") else node["status"]
            repeat = node_id in seen and any(e["target"] == node_id for e in self.edges)
            lines.append(f"{'  ' * depth}{node['label']}  [{by}]{'  (see above)' if repeat else ''}")
            if node_id not in seen:
                seen.add(node_id)
                for edge in self.edges:
                    if edge["target"] == node_id:
                        walk(edge["source"], depth + 1)

        walk(self.target, 0)
        return "\n".join(lines)

    def as_mermaid(self) -> str:
        """A flowchart: artifacts as nodes, each edge labelled with the task that made its target."""
        names = {node_id: f"n{i}" for i, node_id in enumerate(self.nodes)}
        lines = ["flowchart LR"]
        for node_id, node in self.nodes.items():
            note = "" if node["status"] == "traced" else f"<br/>({node['status']})"
            lines.append(f'  {names[node_id]}["{node["label"]}{note}"]')
        for edge in self.edges:
            lines.append(f"  {names[edge['source']]} -->|{Path(edge['task']).name}| {names[edge['target']]}")
        return "\n".join(lines)


class _Walk:
    def __init__(self, start: Path):
        checkout, main = _checkouts_of(start)
        self.roots = list(dict.fromkeys([checkout, main]))
        self.tasks: dict[str, Path] = {}  # id -> directory relative to the repo
        for root in self.roots:
            for task in task_dirs(root):
                rel = task.relative_to(root)
                text = (task / INPUTS_FILE).read_text() if (task / INPUTS_FILE).exists() else ""
                found = (yaml.safe_load(text) or {}).get("task")
                if found and self.tasks.setdefault(str(found), rel) != rel:
                    raise ValueError(
                        f"Task id {found} is in both {self.tasks[str(found)]} and {rel}: a copied task directory? "
                        f"Remove the `task:` line from the copy's {INPUTS_FILE}."
                    )
        self.trace = Trace(target="")
        self._expanded: set[str] = set()

    def relative(self, path: str | Path) -> Path:
        """``path`` relative to the repo when it is inside one of its checkouts; else as given, absolute."""
        path = Path(path).expanduser()  # `~/...` names a per-user cache, such as a downloaded model
        if not path.is_absolute():
            return path
        for root in self.roots:
            if path.is_relative_to(root):
                return path.relative_to(root)
        return path

    def on_disk(self, rel: Path) -> Path:
        """Where ``rel`` is: tracked files in this checkout, shared data and untracked outputs in the main one."""
        return next((root / rel for root in self.roots if (root / rel).exists()), self.roots[-1] / rel)

    def node(self, node_id: str, **fields) -> str:
        self.trace.nodes.setdefault(node_id, fields)
        return node_id

    def leaf(self, rel: Path, key: str | None = None) -> str:
        outside = rel.is_absolute() or (rel.parts[:1] == ("data",) and bool(SOURCE_DIRS & set(rel.parts[2:3])))
        label = f"{rel.name}: {key}" if key else "/".join(rel.parts[-3:])
        return self.node(f"{rel}#{key}" if key else str(rel), label=label, status="source" if outside else "no record")

    def made_by(self, node_id: str, task: Path) -> None:
        """Add the inputs of ``task`` as what ``node_id`` was made from."""
        if node_id in self._expanded:
            return
        self._expanded.add(node_id)
        inputs = declared(self.on_disk(task))
        if inputs is None:
            if str(task) not in self.trace.undeclared:
                self.trace.undeclared.append(str(task))
            return
        for entry in inputs:
            rel = self.relative(entry["path"])
            for key in entry.get("keys") or [None]:
                for source in self.artifacts(rel, key):
                    if source != node_id and self.trace.nodes[source].get("task") != str(task):
                        edge = {"source": source, "target": node_id, "task": str(task)}
                        if edge not in self.trace.edges:
                            self.trace.edges.append(edge)

    def artifacts(self, rel: Path, key: str | None) -> list[str]:
        """The node, or for a whole store (``*``) the nodes, that ``rel`` and ``key`` name; traced further back."""
        if key is None:
            task = owner(rel)
            if task is None:
                return [self.leaf(rel)]
            node_id = self.node(str(rel), label="/".join(rel.parts[-3:]), status="traced", task=str(task))
            self.made_by(node_id, task)
            return [node_id]
        found = records(self.on_disk(rel))
        if key != "*":
            found = [record for record in found if key in record["keys"]][-1:]  # the newest that names it
        if not found:
            return [self.leaf(rel, None if key == "*" else key)]
        nodes = []
        for record in found:
            node_id = f"{rel}@{record['at']}"
            task = self.tasks.get(record["task"])
            if node_id not in self.trace.nodes:
                self.node(
                    node_id,
                    store=str(rel),
                    keys=[],
                    written=len(record["keys"]),
                    status="traced" if task else f"task not in this checkout: {record['path']} on {record['branch']}",
                    task=str(task) if task else None,
                )
            node = self.trace.nodes[node_id]
            node["keys"] = sorted({*node["keys"], *(record["keys"] if key == "*" else [key])})
            shown = ", ".join(node["keys"][:3]) + (f" (+{len(node['keys']) - 3})" if len(node["keys"]) > 3 else "")
            node["label"] = f"{rel.name}: {shown}"
            if task:
                self.made_by(node_id, task)
            nodes.append(node_id)
        return nodes


def trace(artifact: str | Path, key: str | None = None, *, start: str | Path = ".") -> Trace:
    """Trace one artifact back to the data no task made.

    Parameters
    ----------
    artifact
        A store in shared storage, with ``key``; or a file, such as one in a task's ``outputs/``.
    key
        The key in the store, as its records name it: ``obs/leiden``, ``X``, ``shapes/cells``,
        ``tables/table/obs/leiden``.
    start
        Any path in the checkout to trace from; its tasks are read first, then the main checkout's.

    Returns
    -------
    The graph. ``undeclared`` lists the tasks on the path whose ``inputs.yaml`` lists no inputs yet; the trace
    stops at each of them.
    """
    walk = _Walk(Path(start).resolve())
    rel = walk.relative(Path(artifact).resolve())
    walk.trace.target = walk.artifacts(rel, key)[0]
    walk.trace.undeclared.sort()
    return walk.trace


def missing_inputs(task: Path) -> list[str]:
    """The declared inputs of ``task`` that are not there: a path that does not exist, a key its store lacks."""
    walk = _Walk(task)
    missing = []
    for entry in declared(task) or []:
        path = walk.on_disk(walk.relative(entry["path"]))
        if not path.exists():
            missing.append(str(entry["path"]))
        elif wanted := [k for k in entry.get("keys") or [] if k != "*"]:
            missing += [f"{entry['path']}: {k}" for k in sorted(set(wanted) - keys(path))]
    return missing


def changed_since_declared(task: Path) -> bool:
    """Whether the task's scripts or notebooks changed, in git, after its ``inputs.yaml`` was last written."""

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=task, capture_output=True, text=True).stdout.strip()

    code = ("scripts", "notebooks")
    if git("status", "--porcelain", "--", INPUTS_FILE):
        return False  # being written now
    committed = int(git("log", "-1", "--format=%ct", "--", *code) or 0)
    return committed > int(git("log", "-1", "--format=%ct", "--", INPUTS_FILE) or 0) or bool(
        git("status", "--porcelain", "--", *code)
    )
