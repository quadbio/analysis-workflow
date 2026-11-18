"""A trace drawn as a graph of tasks, as DOT text for Graphviz.

One small node per task, in three bands. The bar names the task, its author and date. The shaded band is what
the task consumed that no task made, so the trace ends there: one row per place it lives in, a coloured bar saying
which place (source data in this repo, or one colour per place outside it, the same in every figure of a repo),
then the first few items. The white band is what the task produced on this path. One arrow runs from a task to
each task that consumed what it produced. Above the graph are a title and a small legend of the bars.

Graphviz places the nodes and routes the arrows, so the picture stays compact as tasks are added. Which files and
keys exactly is what the trace's tree lists.
"""

import datetime
import shutil
import subprocess
from collections import defaultdict
from html import escape
from pathlib import Path

from analysis_workflow.paths import _checkouts_of, task_field
from analysis_workflow.trace import Trace, declared, task_dirs

#: Hues of a palette checked for colour-vision deficiencies: what a task produced; source data in this repo;
#: then, in this order, the places outside the repo sorted by name. A seventh place outside gets the neutral,
#: told apart by its name in the legend.
PRODUCED, HERE = "produced", "this repo"
PRODUCED_COLOUR, HERE_COLOUR = "#2a78d6", "#1baf7a"
OUTSIDE = ("#eb6834", "#eda100", "#e87ba4", "#6250d6", "#e34948", "#008300")
INK, SECONDARY, MUTED, BAND, SURFACE = "#0b0b0b", "#52514e", "#898781", "#efeee9", "#fcfcfb"
FONT = "Helvetica"
#: How many items a place names before counting the rest.
SHOWN = 3
#: Point sizes: the title, a task's name, what it produced, the small print (what it consumed, author and date,
#: the legend), and the blank line above and below the legend.
TITLE, NAME, BODY, SMALL, GAP = 8, 7, 6, 5, 3
#: Characters per line that give a node's two bands about the same width; and those of the title and legend,
#: about as wide as a node.
WRAP = {BODY: 54, SMALL: 64}
HEAD = 80
#: The task that is not in this checkout: a branch that is not merged, or a task that was removed.
ELSEWHERE = "task not in this checkout"


def _origin(path: str) -> tuple[str, str]:
    """Where a path that no task made lives, HERE or the name of a place outside the repo, and a short name.

    In the repo, the name is the folder under `data/<dataset>/` and the last two parts of the path; outside, its
    last part, or its last two under the home directory.
    """
    p, home = Path(path).expanduser(), Path.home()
    if not p.is_absolute():
        parts = p.parts[2:] if p.parts[0] == "data" and len(p.parts) > 3 else p.parts
        return HERE, "/".join(parts) if len(parts) <= 3 else f"{parts[0]}/…/{'/'.join(parts[-2:])}"
    for parent in p.parents:
        if (parent / ".git").exists() and not home.is_relative_to(parent):  # a home directory under version control
            return parent.name, p.name
    return ("home directory", "/".join(p.parts[-2:])) if p.is_relative_to(home) else ("outside any repo", str(p))


def _colours(roots: list[Path]) -> dict[str, str]:
    """The colour of each place source data comes from, over all tasks of the repo: the same in every figure."""
    places = set()
    for root in roots:
        for task in task_dirs(root):
            places |= {_origin(str(entry["path"]))[0] for entry in declared(task) or []}
    places.discard(HERE)
    outside = {place: OUTSIDE[i] if i < len(OUTSIDE) else SECONDARY for i, place in enumerate(sorted(places))}
    return {HERE: HERE_COLOUR, **outside}


def _summary(found: Trace) -> tuple[dict[str, dict[str, list[str]]], set[tuple[str, str]]]:
    """Per task on the path the names of what it produced and of what it consumed, by where that lives.

    Also which task consumed which task's work. The artifact asked about is marked by a leading ``▶``.
    """
    tasks = defaultdict(lambda: defaultdict(list))
    for node, fields in found.nodes.items():
        if task := fields.get("task"):
            name = Path(fields["store"]).name if "store" in fields else Path(node).name
            if "store" in fields:
                name += f": {fields['keys'][0]}" if len(fields["keys"]) == 1 else f" ({len(fields['keys'])} keys)"
            tasks[task][PRODUCED].insert(0, "▶ " + name) if node == found.target else tasks[task][PRODUCED].append(name)
    edges, keys = set(), defaultdict(lambda: defaultdict(set))
    for edge in found.edges:
        source = found.nodes[edge["source"]]
        if maker := source.get("task"):
            if maker != edge["task"]:
                edges.add((maker, edge["task"]))
            continue
        path, _, key = edge["source"].partition("#")
        place, name = _origin(path.partition("@")[0])  # a store's write-back is named `<store>@<when>`
        status = ELSEWHERE if source["status"].startswith(ELSEWHERE) else source["status"]
        name += "" if status == "source" else f" ({status})"
        if name not in tasks[edge["task"]][place]:
            tasks[edge["task"]][place].append(name)
        keys[edge["task"]][(place, name)] |= set(source.get("keys") or ([key] if key else []))
    for task, counted in keys.items():  # a store consumed by key shows how many
        for (place, name), found_keys in counted.items():
            if found_keys:
                tasks[task][place][tasks[task][place].index(name)] = f"{name} ({len(found_keys)} keys)"
    return tasks, edges


def _listed(names: list[str], size: float) -> list[str]:
    """The first names of a list, " · " between them, in lines of WRAP[size] characters; the rest counted."""
    shown, more = names[:SHOWN], len(names) - SHOWN
    lines, line, used = [], "", 0
    for i, name in enumerate(shown):
        text = name + (" · " if i < len(shown) - 1 else f" +{more}" if more > 0 else "")
        if used and used + len(text) > WRAP[size]:
            lines.append(line)
            line, used = "", 0
        # the artifact asked about is the one thing set in bold
        line += f"<B>{escape(text)}</B>" if name.startswith("▶") else escape(text)
        used += len(text)
    return [*lines, line]


def _rows(entries: list[tuple[str, list[str]]], size: float, ink: str) -> str:
    """Entries of (bar colour, lines of text): a coloured bar down the left of each entry's lines."""
    text = "".join(
        f'<FONT COLOR="{colour}">▌</FONT>{line}<BR ALIGN="LEFT"/>' for colour, lines in entries for line in lines
    )
    return f'<FONT POINT-SIZE="{size}" COLOR="{ink}">{text}</FONT>'


def _node(task: str, header: str, about: dict[str, list[str]], colour: dict[str, str], note: str) -> str:
    """A task's node as a Graphviz HTML-like label: the bar, what was consumed (shaded), what was produced."""
    bar = (
        f'<FONT COLOR="#ffffff" POINT-SIZE="{NAME}"><B>{escape(Path(task).name)}</B></FONT>'
        f'<FONT COLOR="#ffffff" POINT-SIZE="{SMALL}"> &nbsp; {escape(header)}</FONT>'
    )
    consumed = [(colour[place], _listed(about[place], SMALL)) for place in colour if about.get(place)]
    if note:
        band = f'<FONT POINT-SIZE="{SMALL}" COLOR="{MUTED}">{note}</FONT>'
    else:
        band = _rows(consumed, SMALL, SECONDARY) if consumed else ""
    bands = f'<TR><TD ALIGN="LEFT" BGCOLOR="{SECONDARY}">{bar}</TD></TR>'
    if band:
        bands += f'<TR><TD ALIGN="LEFT" BGCOLOR="{BAND}">{band}</TD></TR>'
    produced = _rows([(PRODUCED_COLOUR, _listed(about[PRODUCED], BODY))], BODY, INK)
    bands += f'<TR><TD ALIGN="LEFT" BGCOLOR="#ffffff">{produced}</TD></TR>'
    return (
        f'"{task}" [label=<<TABLE BORDER="1" COLOR="{SECONDARY}" CELLBORDER="0" CELLSPACING="0" CELLPADDING="1">'
        f"{bands}</TABLE>>];"
    )


def _legend(used: list[str], colour: dict[str, str]) -> str:
    """The legend under the title: lines of small grey text, each coloured bar followed by what it marks.

    No line is longer than HEAD characters, with a little space above and below.
    """

    def bar(shade: str, text: str) -> str:
        return f'<FONT COLOR="{shade}">▌</FONT>{escape(text)}'

    lines = [f"{bar(PRODUCED_COLOUR, 'produced by the task, consumed below')} &nbsp; <B>▶</B> the artifact asked about"]
    if used:
        lines.append("consumed by the task, not further traceable; by where it lives:")
        line, length = "", 0
        for place in used:
            if length and length + len(place) + 3 > HEAD:
                lines.append(line)
                line, length = "", 0
            line, length = line + bar(colour[place], place) + " &nbsp;", length + len(place) + 3
        lines.append(line)
    gap = f'<FONT POINT-SIZE="{GAP}"> <BR ALIGN="LEFT"/></FONT>'
    text = "".join(f'{line}<BR ALIGN="LEFT"/>' for line in lines)
    return f'{gap}<FONT POINT-SIZE="{SMALL}" COLOR="{MUTED}">{text}</FONT>{gap}'


def dot(found: Trace, start: str | Path = ".", *, today: datetime.date | None = None) -> str:
    """The trace ``found`` as DOT text: the tasks its artifact rests on, back to the data no task made.

    Parameters
    ----------
    start
        Any path in the checkout the trace was run from; its tasks' READMEs give the authors and dates.
    today
        The date in the title; by default, today's.

    Raises
    ------
    ValueError
        If no task made the artifact: there is nothing to draw.
    """
    target = found.nodes[found.target]
    if target.get("task") is None:
        raise ValueError(f"No task made {target['label']} ({target['status']}): there is nothing to draw.")
    roots = list(dict.fromkeys(_checkouts_of(start)))
    about, edges = _summary(found)
    colour, consumers = _colours(roots), {consumer for _, consumer in edges}
    used = [place for place in colour if any(place in lists for lists in about.values())]

    def header(task: str) -> tuple[str, str]:
        """A task's author and date, from its README in the first checkout that has the task."""
        where = next((root / task for root in roots if (root / task / "README.md").exists()), roots[-1] / task)
        return task_field(where, "Author") or "", task_field(where, "Date") or ""

    name = (
        Path(target["store"]).name + ": " + ", ".join(target["keys"]) if "store" in target else Path(found.target).name
    )
    when = escape(f"on {today or datetime.date.today()} in {roots[-1].name}")
    # a long artifact name takes the title line to itself
    joint = '<BR ALIGN="LEFT"/>' if len(name) + len(when) > HEAD else " &nbsp;"
    lines = [
        "digraph trace {",
        f'  graph [rankdir=TB, bgcolor="{SURFACE}", pad=0.06, nodesep=0.12, ranksep=0.16, fontname="{FONT}", '
        "labelloc=t, labeljust=l,",
        f'    label=<<FONT POINT-SIZE="{TITLE}"><B>Tracing {escape(name)}</B></FONT>'
        f'<FONT POINT-SIZE="{SMALL}" COLOR="{SECONDARY}">{joint}{when}</FONT><BR ALIGN="LEFT"/>'
        f"{_legend(used, colour)}>];",
        f'  node [shape=plain, fontname="{FONT}"];',
        f'  edge [penwidth=0.7, arrowsize=0.45, color="{SECONDARY}"];',
    ]
    for task in sorted(about, key=lambda t: (header(t)[1], t)):  # the oldest task first
        sourced = any(place != PRODUCED for place in about[task])
        missing = "inputs not declared" if task in found.undeclared else "no inputs declared"
        note = missing if task in found.undeclared or not (sourced or task in consumers) else ""
        lines.append("  " + _node(task, " · ".join(filter(None, header(task))), about[task], colour, note))
    lines += [f'  "{maker}" -> "{consumer}";' for maker, consumer in sorted(edges)]
    return "\n".join([*lines, "}"]) + "\n"


def render(source: str, output: str | Path) -> Path:
    """Draw DOT text ``source`` into ``output`` with Graphviz; the suffix picks the file type (.pdf, .svg, .png).

    Raises
    ------
    RuntimeError
        If Graphviz's ``dot`` is not on PATH.
    """
    output = Path(output)
    if shutil.which("dot") is None:
        raise RuntimeError(
            "Graphviz's `dot` is not on PATH. It is a conda package: in a pixi project, `pixi add graphviz`."
        )
    subprocess.run(
        ["dot", f"-T{output.suffix.lstrip('.') or 'pdf'}", "-o", str(output)], input=source, text=True, check=True
    )
    return output
