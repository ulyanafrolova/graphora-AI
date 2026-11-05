"""Answer types for graph queries, canonical JSON and readable text (specs/004-graph-queries data-model.md,
contracts/answers.md)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

from graphora.graph.model import Edge
from graphora.graph.serialize import _edge_dict

LinkConfidence = Literal["resolved", "heuristic"]
Question = Literal["dependencies", "dependents", "impact", "neighbors", "cycles", "key_files"]


def strongest(confidences: Iterable[str]) -> LinkConfidence:
    """A link is a fact if any of its edges is resolved (research § R4)."""
    return "resolved" if "resolved" in set(confidences) else "heuristic"


def weakest(confidences: Iterable[str]) -> LinkConfidence:
    """A chain is only as sure as its least sure link (research § R4)."""
    return "heuristic" if "heuristic" in set(confidences) else "resolved"


@dataclass(frozen=True)
class Link:
    source: str
    target: str
    edges: tuple[Edge, ...]
    confidence: LinkConfidence
    type_only: bool
    via: tuple[Edge, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "confidence": self.confidence,
            "type_only": self.type_only,
            "edges": [_edge_dict(e) for e in self.edges],
            "via": [_edge_dict(e) for e in self.via],
        }


@dataclass(frozen=True)
class Item:
    node: str
    kind: str
    chain: tuple[Link, ...] = ()
    confidence: LinkConfidence = "resolved"
    type_only: bool = False
    distance: int | None = None
    transitive_dependents: int | None = None
    direct_dependents: int | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "node": self.node,
            "kind": self.kind,
            "confidence": self.confidence,
            "type_only": self.type_only,
            "chain": [link.to_dict() for link in self.chain],
        }
        if self.distance is not None:
            out["distance"] = self.distance
        if self.transitive_dependents is not None:
            out["transitive_dependents"] = self.transitive_dependents
        if self.direct_dependents is not None:
            out["direct_dependents"] = self.direct_dependents
        return out


@dataclass(frozen=True)
class CycleGroup:
    files: tuple[str, ...]
    cycle: tuple[Link, ...]
    type_only: bool
    confidence: LinkConfidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": list(self.files),
            "cycle": [link.to_dict() for link in self.cycle],
            "type_only": self.type_only,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class Completeness:
    unresolved_imports: int
    not_analyzed_files: int
    files_with_errors: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "unresolved_imports": self.unresolved_imports,
            "not_analyzed_files": self.not_analyzed_files,
            "files_with_errors": self.files_with_errors,
        }


@dataclass(frozen=True)
class Answer:
    """`None` marks a field the question does not use; it is left out of the JSON (contracts/answers.md)."""

    snapshot: str
    question: Question
    target: str | None
    options: dict[str, Any]
    total: int
    truncated: bool
    items: tuple[Item, ...] | None = None
    incoming: tuple[Item, ...] | None = None
    outgoing: tuple[Item, ...] | None = None
    unresolved: tuple[Edge, ...] | None = None
    groups: tuple[CycleGroup, ...] | None = None
    cut: bool | None = None
    completeness: Completeness | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "snapshot": self.snapshot,
            "question": self.question,
            "target": self.target,
            "options": dict(self.options),
            "total": self.total,
            "truncated": self.truncated,
        }
        for name in ("items", "incoming", "outgoing", "groups"):
            value = getattr(self, name)
            if value is not None:
                out[name] = [x.to_dict() for x in value]
        if self.unresolved is not None:
            out["unresolved"] = [_edge_dict(e) for e in self.unresolved]
        if self.cut is not None:
            out["cut"] = self.cut
        if self.completeness is not None:
            out["completeness"] = self.completeness.to_dict()
        return out


def dumps(answer: Answer) -> bytes:
    text = json.dumps(answer.to_dict(), sort_keys=True, ensure_ascii=False, indent=2)
    return (text + "\n").encode("utf-8")


def _name(node_id: str) -> str:
    """`file:a.py` and `asset:x.css` read as paths; `ext:npm:react` as `npm:react`."""
    return node_id.partition(":")[2]


def _chain_text(chain: tuple[Link, ...]) -> str:
    """`a.py:3 → b.py:7 → target.py`; a barrel link adds its re-export lines (`app.ts:1 → index.ts:2 → Card.tsx`)."""
    steps = []
    for link in chain:
        steps.append(f"{_name(link.source)}:{link.edges[0].line}")
        steps += [f"{_name(e.source)}:{e.line}" for e in link.via]
    return " → ".join(steps + [_name(chain[-1].target)])


def _marks(item: Item) -> str:
    return (" (likely)" if item.confidence == "heuristic" else "") + (" (type-only)" if item.type_only else "")


def _item_lines(answer: Answer) -> list[str]:
    lines = []
    for item in answer.items or ():
        distance = f"  [{item.distance}]" if item.distance is not None else ""
        lines.append(f"{_name(item.node)}{distance}  {_chain_text(item.chain)}{_marks(item)}")
    for e in answer.unresolved or ():
        reference = e.target.split(":", 2)[2]
        lines.append(f"line {e.line}: {reference} (unresolved: {e.reason})")
    return lines


def _neighbor_lines(answer: Answer) -> list[str]:
    lines = ["imports:"]
    lines += [f"  {_chain_text(i.chain)}{_marks(i)}" for i in answer.outgoing or ()]
    lines.append("imported by:")
    lines += [f"  {_chain_text(i.chain)}{_marks(i)}" for i in answer.incoming or ()]
    return lines + _item_lines(answer)


def _key_file_lines(answer: Answer) -> list[str]:
    return [
        f"{_name(i.node)}  transitive {i.transitive_dependents}  direct {i.direct_dependents}" for i in answer.items or ()
    ]


def _group_lines(answer: Answer) -> list[str]:
    lines = []
    for n, group in enumerate(answer.groups or (), start=1):
        marks = (" (likely)" if group.confidence == "heuristic" else "") + (" (type-only)" if group.type_only else "")
        lines.append(f"cycle {n}: {', '.join(_name(f) for f in group.files)}{marks}")
        lines.append(f"  {_chain_text(group.cycle)}")
    return lines


def _header(answer: Answer) -> list[str]:
    target = f" {_name(answer.target)}" if answer.target else ""
    return [f"{answer.question}{target} @ {answer.snapshot}"]


_RENDERERS: dict[str, Callable[[Answer], list[str]]] = {
    "dependencies": _item_lines,
    "dependents": _item_lines,
    "impact": _item_lines,
    "cycles": _group_lines,
    "neighbors": _neighbor_lines,
    "key_files": _key_file_lines,
}


def _footer(answer: Answer) -> list[str]:
    lines = [f"total: {answer.total}"]
    if answer.truncated:
        lines.append(f"truncated (limit {answer.options.get('limit')})")
    if answer.cut:
        lines.append(f"cut at depth {answer.options.get('max_depth')}")
    if answer.completeness is not None:
        c = answer.completeness
        lines.append(
            f"completeness: {c.unresolved_imports} unresolved imports, {c.not_analyzed_files} files not analyzed, "
            f"{c.files_with_errors} files with errors"
        )
    return lines


def render_text(answer: Answer) -> str:
    body = _RENDERERS[answer.question](answer) if answer.question in _RENDERERS else []
    return "\n".join(_header(answer) + body + _footer(answer)) + "\n"
