"""The one graph query layer: an index over a graph document and the questions asked of it (constitution VII,
specs/004-graph-queries research § R3–R10). API, MCP, agents and the verifier call these functions."""

from __future__ import annotations

from collections import defaultdict
from typing import TypeVar

import networkx as nx

from graphora.graph.model import CoverageFile, Edge, GraphDocument, Node, UnresolvedNode
from graphora.graph.results import Completeness, Link, strongest
from graphora.graph.serialize import edge_sort_key

T = TypeVar("T")


class NodeNotFound(Exception):
    """`status`: detected_only, not_code, a skip reason, ambiguous, invalid_path or not_in_snapshot."""

    def __init__(self, target: str, status: str, message: str) -> None:
        super().__init__(message)
        self.target = target
        self.status = status
        self.message = message


class GraphIndex:
    """Built once per document by `index()`; read-only afterwards, so queries can share it."""

    def __init__(self, doc: GraphDocument) -> None:
        self.doc = doc
        self.nodes: dict[str, Node] = {n.id: n for n in sorted(doc.nodes, key=lambda n: n.id)}
        self.coverage: dict[str, CoverageFile] = {f.path: f for f in doc.files}

        pairs: dict[tuple[str, str], list[Edge]] = defaultdict(list)
        unresolved: dict[str, list[Edge]] = defaultdict(list)
        for e in doc.edges:
            if e.confidence == "unresolved":
                unresolved[e.source].append(e)
            else:
                pairs[(e.source, e.target)].append(e)
        self.unresolved: dict[str, tuple[Edge, ...]] = {
            source: tuple(sorted(edges, key=edge_sort_key)) for source, edges in sorted(unresolved.items())
        }
        self.links = _digraph(
            [i for i, n in self.nodes.items() if not isinstance(n, UnresolvedNode)],
            {pair: tuple(sorted(edges, key=edge_sort_key)) for pair, edges in pairs.items()},
        )
        self._runtime_links: nx.DiGraph | None = None

        flagged = sum(1 for f in doc.files if f.status == "analyzed" and f.flags)
        self.completeness = Completeness(
            unresolved_imports=sum(len(edges) for edges in self.unresolved.values()),
            not_analyzed_files=sum(1 for f in doc.files if f.status == "detected_only"),
            files_with_errors=flagged,
        )

    def link(self, source: str, target: str, include_type_only: bool = True) -> Link:
        edges = _links(self, include_type_only).edges[source, target]["edges"]
        return Link(
            source=source,
            target=target,
            edges=edges,
            confidence=strongest(e.confidence for e in edges),
            type_only=all(e.type_only for e in edges),
        )


def _digraph(nodes: list[str], pairs: dict[tuple[str, str], tuple[Edge, ...]]) -> nx.DiGraph:
    """Nodes and links are inserted in sorted id order, so NetworkX iteration order is fixed (FR-015)."""
    g = nx.DiGraph()
    g.add_nodes_from(sorted(nodes))
    for pair in sorted(pairs):
        g.add_edge(*pair, edges=pairs[pair])
    return g


def index(doc: GraphDocument) -> GraphIndex:
    return GraphIndex(doc)


def _links(ix: GraphIndex, include_type_only: bool) -> nx.DiGraph:
    """The link graph; without type-only edges a link keeps its other edges or disappears (research § R3)."""
    if include_type_only:
        return ix.links
    if ix._runtime_links is None:
        pairs = {}
        for source, target, data in ix.links.edges(data=True):
            kept = tuple(e for e in data["edges"] if not e.type_only)
            if kept:
                pairs[(source, target)] = kept
        ix._runtime_links = _digraph(list(ix.links.nodes), pairs)
    return ix._runtime_links


def _limit(items: list[T], limit: int | None) -> tuple[list[T], int, bool]:
    if limit is not None and limit < 0:
        raise ValueError(f"limit must be 0 or more, got {limit}")
    total = len(items)
    if limit is None:
        return items, total, False
    return items[:limit], total, total > limit


def _skip_reason(ix: GraphIndex, path: str) -> str | None:
    for s in ix.doc.skipped:
        if path == s.path or path.startswith(s.path + "/"):
            return s.reason
    return None


def resolve(ix: GraphIndex, target: str) -> str:
    """A node id from an id, a repository-relative path or an external package name (research § R10)."""
    if target in ix.nodes:
        return target

    if "\\" in target or target.startswith("/") or ".." in target.split("/"):
        raise NodeNotFound(target, "invalid_path", f"{target} is not a repository-relative path (no '\\', '/' at the start or '..')")
    path = target
    while path.startswith("./"):
        path = path[2:]
    path = path.rstrip("/")
    for node_id in (f"file:{path}", f"asset:{path}"):
        if node_id in ix.nodes:
            return node_id

    externals = [i for i in (f"ext:npm:{target}", f"ext:python:{target}") if i in ix.nodes]
    if len(externals) == 1:
        return externals[0]
    if externals:
        raise NodeNotFound(target, "ambiguous", f"{target} is ambiguous: use {' or '.join(externals)}")

    covered = ix.coverage.get(path)
    if covered is not None and covered.status != "analyzed":
        raise NodeNotFound(target, covered.status, f"{target} is {covered.status} (not analyzed)")
    reason = _skip_reason(ix, path)
    if reason is not None:
        raise NodeNotFound(target, reason, f"{target} is skipped ({reason})")
    raise NodeNotFound(target, "not_in_snapshot", f"{target} is not in snapshot {ix.doc.snapshot}")
