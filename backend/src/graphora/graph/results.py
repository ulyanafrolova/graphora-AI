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
Question = Literal["dependencies", "dependents", "impact", "neighbors", "cycles", "key_files", "definitions"]


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
    declared: tuple[Edge, ...] = ()  # 009: project level, the declared project or package reference

    def to_dict(self) -> dict[str, Any]:
        out = {
            "source": self.source,
            "target": self.target,
            "confidence": self.confidence,
            "type_only": self.type_only,
            "edges": [_edge_dict(e) for e in self.edges],
            "via": [_edge_dict(e) for e in self.via],
        }
        if self.declared:
            out["declared"] = [_edge_dict(e) for e in self.declared]
        return out


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
    declared_only: bool = False  # 009: a declared reference that no code uses

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
        if self.declared_only:
            out["declared_only"] = True
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
class DefinitionMatch:
    """A definition found by name (specs/006-mcp-server data-model.md § DefinitionMatch)."""

    file: str
    path: str
    line: int
    kind: str
    name: str
    exported_as: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"file": self.file, "path": self.path, "line": self.line, "kind": self.kind, "name": self.name}
        if self.exported_as is not None:
            out["exported_as"] = sorted(set(self.exported_as))
        return out


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
    definitions: tuple[DefinitionMatch, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "snapshot": self.snapshot,
            "question": self.question,
            "target": self.target,
            "options": dict(self.options),
            "total": self.total,
            "truncated": self.truncated,
        }
        for name in ("items", "incoming", "outgoing", "groups", "definitions"):
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


@dataclass(frozen=True)
class Overview:
    """What a graph covers (specs/006-mcp-server data-model.md § Overview)."""

    snapshot: str
    schema_version: int
    extractors: dict[str, str]
    languages: dict[str, int]
    files: dict[str, int]
    nodes: dict[str, int]
    edges: int
    unresolved_imports: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot,
            "schema_version": self.schema_version,
            "extractors": dict(self.extractors),
            "languages": dict(self.languages),
            "files": dict(self.files),
            "nodes": dict(self.nodes),
            "edges": self.edges,
            "unresolved_imports": self.unresolved_imports,
        }


def dumps(answer: Answer | Overview) -> bytes:
    text = json.dumps(answer.to_dict(), sort_keys=True, ensure_ascii=False, indent=2)
    return (text + "\n").encode("utf-8")


def _name(node_id: str) -> str:
    """`file:a.py` and `asset:x.css` read as paths; `ext:npm:react` as `npm:react`."""
    return node_id.partition(":")[2]


def _chain_text(chain: tuple[Link, ...]) -> str:
    """`a.py:3 → b.py:7 → target.py`; a barrel link adds its re-export lines (`app.ts:1 → index.ts:2 → Card.tsx`)."""
    steps = []
    for link in chain:
        first = link.edges[0]  # at project level the edge starts in a file of the source project
        more = f" (+{len(link.edges) - 1} more)" if link.source.startswith("project:") and len(link.edges) > 1 else ""
        steps.append(f"{_name(first.source)}:{first.line}{more}")
        steps += [f"{_name(e.source)}:{e.line}" for e in link.via]
    return " → ".join(steps + [_name(chain[-1].target)])


def _marks(item: Item) -> str:
    declared = " (declared, not used by code)" if item.declared_only else ""
    return (" (likely)" if item.confidence == "heuristic" else "") + (" (type-only)" if item.type_only else "") + declared


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


def _definition_lines(answer: Answer) -> list[str]:
    lines = []
    for d in answer.definitions or ():
        exported = f"  exported as {', '.join(sorted(set(d.exported_as)))}" if d.exported_as else ""
        lines.append(f"{d.path}:{d.line}  {d.kind}  {d.name}{exported}")
    return lines


def _header(answer: Answer) -> list[str]:
    target = f" {_name(answer.target)}" if answer.target else ""
    if answer.question == "definitions":
        target = f" {answer.options['name']}"
    return [f"{answer.question}{target} @ {answer.snapshot}"]


_RENDERERS: dict[str, Callable[[Answer], list[str]]] = {
    "dependencies": _item_lines,
    "dependents": _item_lines,
    "impact": _item_lines,
    "cycles": _group_lines,
    "neighbors": _neighbor_lines,
    "key_files": _key_file_lines,
    "definitions": _definition_lines,
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


def _overview_text(o: Overview) -> str:
    def pairs(values: dict[str, Any]) -> str:
        return ", ".join(f"{k} {v}" for k, v in sorted(values.items())) or "none"

    f, n = o.files, o.nodes
    lines = [
        f"overview @ {o.snapshot}",
        f"schema {o.schema_version}, extractors: {pairs(o.extractors)}",
        f"languages: {pairs(o.languages)}",
        f"files: {f['analyzed']} analyzed, {f['detected_only']} detected only, {f['not_code']} not code, "
        f"{f['skipped']} skipped",
        f"nodes: {n['file']} file, {n['external']} external, {n['unresolved']} unresolved, {n['asset']} asset, "
        f"{n['project']} project, {n['solution']} solution",
        f"edges: {o.edges} ({o.unresolved_imports} unresolved imports)",
    ]
    return "\n".join(lines) + "\n"


def render_text(answer: Answer | Overview) -> str:
    if isinstance(answer, Overview):
        return _overview_text(answer)
    body = _RENDERERS[answer.question](answer) if answer.question in _RENDERERS else []
    return "\n".join(_header(answer) + body + _footer(answer)) + "\n"
