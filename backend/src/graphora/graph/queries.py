"""The one graph query layer: an index over a graph document and the questions asked of it (constitution VII,
specs/004-graph-queries research § R3–R10). API, MCP, agents and the verifier call these functions."""

from __future__ import annotations

from collections import defaultdict
from typing import TypeVar

import networkx as nx

from graphora.graph.model import CoverageFile, Edge, GraphDocument, Node, UnresolvedNode
from graphora.graph.results import Answer, Completeness, Item, Link, Question, strongest, weakest
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
        return _make_link(source, target, _links(self, include_type_only).edges[source, target]["edges"])


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


# --- questions ----------------------------------------------------------------------------------------------


def _kind(node_id: str) -> str:
    return {"file": "file", "ext": "external", "asset": "asset"}[node_id.split(":", 1)[0]]


def _make_link(source: str, target: str, edges: tuple[Edge, ...]) -> Link:
    return Link(source, target, edges, strongest(e.confidence for e in edges), all(e.type_only for e in edges))


def _item(node: str, chain: tuple[Link, ...], distance: int | None = None) -> Item:
    return Item(
        node=node,
        kind=_kind(node),
        chain=chain,
        confidence=weakest(link.confidence for link in chain),
        type_only=any(link.type_only for link in chain),
        distance=distance,
    )


def _check_depth(max_depth: int | None) -> None:
    if max_depth is not None and max_depth < 1:
        raise ValueError(f"max_depth must be 1 or more, got {max_depth}")


def _answer(ix: GraphIndex, question: Question, target: str | None, options: dict, items: list[Item], limit: int | None, **extra) -> Answer:
    shown, total, truncated = _limit(items, limit)
    return Answer(
        snapshot=ix.doc.snapshot,
        question=question,
        target=target,
        options=options,
        total=total,
        truncated=truncated,
        items=tuple(shown),
        completeness=ix.completeness,
        **extra,
    )


def dependencies(ix: GraphIndex, target: str, *, include_type_only: bool = True, limit: int | None = None) -> Answer:
    """What the node imports or re-exports, one item per target in id order (FR-004)."""
    _limit([], limit)
    node = resolve(ix, target)
    g = _links(ix, include_type_only)
    items = [_item(dep, (ix.link(node, dep, include_type_only),)) for dep in sorted(g.successors(node))]
    unresolved = tuple(e for e in ix.unresolved.get(node, ()) if include_type_only or not e.type_only)
    options = {"include_type_only": include_type_only, "limit": limit}
    return _answer(ix, "dependencies", node, options, items, limit, unresolved=unresolved)


def _matches(e: Edge, symbol: str) -> bool:
    return e.symbol == symbol or (e.type == "reexports" and e.alias == symbol)


def dependents(
    ix: GraphIndex,
    target: str,
    *,
    symbol: str | None = None,
    include_type_only: bool = True,
    follow_barrels: bool = False,
    limit: int | None = None,
) -> Answer:
    """The files that import or re-export the node, one item per file in id order (FR-005)."""
    _limit([], limit)
    if follow_barrels:
        raise NotImplementedError("follow_barrels arrives with user story 4")
    node = resolve(ix, target)
    g = _links(ix, include_type_only)
    items = []
    for dep in sorted(g.predecessors(node)):
        edges = g.edges[dep, node]["edges"]
        if symbol is not None:
            edges = tuple(e for e in edges if _matches(e, symbol))
            if not edges:
                continue
        items.append(_item(dep, (_make_link(dep, node, edges),)))
    options = {"follow_barrels": follow_barrels, "include_type_only": include_type_only, "limit": limit, "symbol": symbol}
    return _answer(ix, "dependents", node, options, items, limit)


def impact(
    ix: GraphIndex,
    target: str,
    *,
    max_depth: int | None = None,
    include_type_only: bool = True,
    follow_barrels: bool = False,
    limit: int | None = None,
) -> Answer:
    """Every file that depends on the node transitively, nearest first, each with one chain to it (FR-006,
    research § R5). Links are walked backwards from the target; only files have dependents, so `ext:` and
    `asset:` nodes are never passed through."""
    _limit([], limit)
    _check_depth(max_depth)
    if follow_barrels:
        raise NotImplementedError("follow_barrels arrives with user story 4")
    node = resolve(ix, target)
    g = _links(ix, include_type_only)

    distance = {node: 0}
    level = [node]
    depth = 0
    while level and (max_depth is None or depth < max_depth):
        depth += 1
        level = sorted({dep for n in level for dep in g.predecessors(n) if dep not in distance})
        for dep in level:
            distance[dep] = depth
    cut = max_depth is not None and any(dep not in distance for n in level for dep in g.predecessors(n))

    def next_hop(n: str) -> str:
        return min(s for s in g.successors(n) if distance.get(s) == distance[n] - 1)

    items = []
    for dep in sorted((n for n in distance if n != node), key=lambda n: (distance[n], n)):
        chain = []
        current = dep
        while current != node:
            hop = next_hop(current)
            chain.append(ix.link(current, hop, include_type_only))
            current = hop
        items.append(_item(dep, tuple(chain), distance[dep]))
    options = {"follow_barrels": follow_barrels, "include_type_only": include_type_only, "limit": limit, "max_depth": max_depth}
    return _answer(ix, "impact", node, options, items, limit, cut=cut)
