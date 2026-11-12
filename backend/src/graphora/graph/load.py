"""Read a graph document back into the model and check it (specs/004-graph-queries research § R2)."""

from __future__ import annotations

import json
from typing import Any, get_args

from graphora.graph import model, serialize
from graphora.graph.model import (
    AssetNode,
    CoverageFile,
    Definition,
    Edge,
    Export,
    ExternalNode,
    FileNode,
    GraphDocument,
    Node,
    ProjectNode,
    Skipped,
    UnresolvedNode,
)

_LANGUAGES = ("python", "typescript", "javascript", "csharp")
_PROJECT_EDGES = ("project_reference", "package_reference")


class InvalidGraph(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _field(obj: Any, key: str, where: str) -> Any:
    if not isinstance(obj, dict):
        raise InvalidGraph(f"{where}: expected an object")
    if key not in obj:
        raise InvalidGraph(f"{where}: missing field '{key}'")
    return obj[key]


def _str(obj: Any, key: str, where: str) -> str:
    value = _field(obj, key, where)
    if not isinstance(value, str):
        raise InvalidGraph(f"{where}.{key}: expected a string")
    return value


def _opt_str(obj: Any, key: str, where: str) -> str | None:
    value = _field(obj, key, where)
    if value is not None and not isinstance(value, str):
        raise InvalidGraph(f"{where}.{key}: expected a string or null")
    return value


def _int(obj: Any, key: str, where: str) -> int:
    value = _field(obj, key, where)
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidGraph(f"{where}.{key}: expected an integer")
    return value


def _bool(obj: Any, key: str, where: str) -> bool:
    value = _field(obj, key, where)
    if not isinstance(value, bool):
        raise InvalidGraph(f"{where}.{key}: expected true or false")
    return value


def _list(obj: Any, key: str, where: str) -> list:
    value = _field(obj, key, where)
    if not isinstance(value, list):
        raise InvalidGraph(f"{where}.{key}: expected a list")
    return value


def _enum(value: Any, allowed: tuple[str, ...], where: str) -> Any:
    if value not in allowed:
        raise InvalidGraph(f"{where}: unknown value {value!r} (expected one of {', '.join(allowed)})")
    return value


def _definition(raw: Any, where: str) -> Definition:
    exported_as = None
    if isinstance(raw, dict) and "exported_as" in raw:
        names = _list(raw, "exported_as", where)
        if not all(isinstance(n, str) for n in names):
            raise InvalidGraph(f"{where}.exported_as: expected a list of strings")
        exported_as = tuple(names)
    return Definition(
        _enum(_str(raw, "kind", where), get_args(model.DefinitionKind), f"{where}.kind"),
        _str(raw, "name", where),
        _int(raw, "line", where),
        exported_as,
    )


def _node(raw: Any, where: str) -> Node:
    kind = _str(raw, "kind", where)
    node: Node
    if kind == "file":
        language = _enum(_str(raw, "language", where), _LANGUAGES, f"{where}.language")
        definitions = tuple(_definition(d, f"{where}.definitions[{i}]") for i, d in enumerate(_list(raw, "definitions", where)))
        exports = None
        if "exports" in raw:
            exports = tuple(
                Export(_str(x, "name", f"{where}.exports[{i}]"), _opt_str(x, "local", f"{where}.exports[{i}]"), _int(x, "line", f"{where}.exports[{i}]"))
                for i, x in enumerate(_list(raw, "exports", where))
            )
        project = _opt_str(raw, "project", where) if isinstance(raw, dict) and "project" in raw else None
        node = FileNode(_str(raw, "path", where), language, definitions, exports, project)
    elif kind == "external":
        node = ExternalNode(
            _str(raw, "name", where),
            _enum(_str(raw, "ecosystem", where), get_args(model.Ecosystem), f"{where}.ecosystem"),
            _enum(_str(raw, "category", where), get_args(model.Category), f"{where}.category"),
        )
    elif kind == "unresolved":
        node = UnresolvedNode(
            _str(raw, "reference", where),
            _enum(_str(raw, "ecosystem", where), get_args(model.Ecosystem), f"{where}.ecosystem"),
        )
    elif kind == "asset":
        node = AssetNode(_str(raw, "path", where))
    elif kind == "project":
        node = ProjectNode(_str(raw, "path", where))
    else:
        raise InvalidGraph(f"{where}.kind: unknown value {kind!r}")
    stored = _str(raw, "id", where)
    if stored != node.id:
        raise InvalidGraph(f"{where}.id: {stored!r} does not match its fields ({node.id!r})")
    return node


def _edge(raw: Any, where: str) -> Edge:
    reason = None
    if isinstance(raw, dict) and "reason" in raw:
        reason = _enum(raw["reason"], get_args(model.Reason), f"{where}.reason")
    alias = _opt_str(raw, "alias", where) if isinstance(raw, dict) and "alias" in raw else None
    directive = None
    global_using = None
    if isinstance(raw, dict) and "directive" in raw:
        directive = _enum(raw["directive"], get_args(model.Directive), f"{where}.directive")
    if isinstance(raw, dict) and "global_using" in raw:
        global_using = _bool(raw, "global_using", where)
    try:
        edge = Edge(
            source=_str(raw, "source", where),
            target=_str(raw, "target", where),
            symbol=_opt_str(raw, "symbol", where),
            line=_int(raw, "line", where),
            column=_int(raw, "column", where),
            snapshot=_str(raw, "snapshot", where),
            confidence=_enum(_str(raw, "confidence", where), get_args(model.Confidence), f"{where}.confidence"),
            reason=reason,
            extractor=_str(raw, "extractor", where),
            snippet_hash=_str(raw, "snippet_hash", where),
            type=_enum(_str(raw, "type", where), get_args(model.EdgeType), f"{where}.type"),
            form=_enum(_str(raw, "form", where), get_args(model.Form), f"{where}.form"),
            type_only=_bool(raw, "type_only", where),
            alias=alias,
            directive=directive,
            global_using=global_using,
        )
    except ValueError as exc:
        raise InvalidGraph(f"{where}: {exc}") from None
    stored = _str(raw, "id", where)
    if stored != serialize.edge_id(edge):
        raise InvalidGraph(f"{where}.id: {stored} does not match its fields ({serialize.edge_id(edge)})")
    return edge


def _check_edges(edges: tuple[Edge, ...], nodes: dict[str, Node], snapshot: str) -> None:
    for i, e in enumerate(edges):
        where = f"edges[{i}]"
        if e.snapshot != snapshot:
            raise InvalidGraph(f"{where}.snapshot: {e.snapshot} differs from the document snapshot {snapshot}")
        if e.type in _PROJECT_EDGES:
            if not isinstance(nodes.get(e.source), ProjectNode):
                raise InvalidGraph(f"{where}.source: {e.source} is not a project node of the document")
        elif not isinstance(nodes.get(e.source), FileNode):
            raise InvalidGraph(f"{where}.source: {e.source} is not a file node of the document")
        if e.target not in nodes:
            raise InvalidGraph(f"{where}.target: {e.target} is not a node of the document")
        if (e.confidence == "unresolved") != isinstance(nodes[e.target], UnresolvedNode):
            raise InvalidGraph(f"{where}: only 'unresolved' edges may point to an unresolved node")


def loads(data: bytes) -> GraphDocument:
    try:
        raw = json.loads(data)
    except ValueError as exc:
        raise InvalidGraph(f"not valid JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise InvalidGraph("a graph document must be a JSON object")
    version = _field(raw, "schema_version", "document")
    if version != serialize.SCHEMA_VERSION:
        raise InvalidGraph(f"schema_version {version!r} is not supported (expected {serialize.SCHEMA_VERSION})")
    snapshot = _str(raw, "snapshot", "document")
    extractors = _field(raw, "extractors", "document")
    if not isinstance(extractors, dict) or not all(isinstance(v, str) for v in extractors.values()):
        raise InvalidGraph("document.extractors: expected an object of version strings")

    nodes: dict[str, Node] = {}
    for i, n in enumerate(_list(raw, "nodes", "document")):
        node = _node(n, f"nodes[{i}]")
        if node.id in nodes:
            raise InvalidGraph(f"nodes[{i}]: duplicate node id {node.id}")
        nodes[node.id] = node
    edges = tuple(_edge(e, f"edges[{i}]") for i, e in enumerate(_list(raw, "edges", "document")))
    _check_edges(edges, nodes, snapshot)

    coverage = _field(raw, "coverage", "document")
    files = tuple(
        CoverageFile(
            _str(f, "path", f"coverage.files[{i}]"),
            _opt_str(f, "language", f"coverage.files[{i}]"),
            _enum(_str(f, "status", f"coverage.files[{i}]"), get_args(model.Status), f"coverage.files[{i}].status"),
            tuple(_enum(x, get_args(model.Flag), f"coverage.files[{i}].flags") for x in _list(f, "flags", f"coverage.files[{i}]")),
            _int(f, "unresolved_type_names", f"coverage.files[{i}]") if isinstance(f, dict) and "unresolved_type_names" in f else None,
        )
        for i, f in enumerate(_list(coverage, "files", "coverage"))
    )
    skipped = tuple(
        Skipped(
            _str(s, "path", f"coverage.skipped[{i}]"),
            _enum(_str(s, "reason", f"coverage.skipped[{i}]"), get_args(model.SkipReason), f"coverage.skipped[{i}].reason"),
        )
        for i, s in enumerate(_list(coverage, "skipped", "coverage"))
    )
    return GraphDocument(snapshot, dict(extractors), tuple(nodes.values()), edges, files, skipped)
