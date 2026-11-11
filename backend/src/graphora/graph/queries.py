"""The one graph query layer: an index over a graph document and the questions asked of it (constitution VII,
specs/004-graph-queries research § R3–R10). API, MCP, agents and the verifier call these functions."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import TypeVar

import networkx as nx

from graphora.graph.model import AssetNode, CoverageFile, Edge, ExternalNode, FileNode, GraphDocument, Node, UnresolvedNode
from graphora.graph.results import Answer, Completeness, CycleGroup, Item, Link, Overview, Question, strongest, weakest
from graphora.graph.serialize import SCHEMA_VERSION, edge_sort_key

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
        self._barrels: dict[bool, dict[tuple[str, str], Link]] = {}

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


def _check_limit(limit: int | None) -> None:
    if limit is not None and limit < 0:
        raise ValueError(f"limit must be 0 or more, got {limit}")


def _limit(items: list[T], limit: int | None) -> tuple[list[T], int, bool]:
    _check_limit(limit)
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
    _check_limit(limit)
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
    """The files that import or re-export the node, one item per file in id order (FR-005). With
    `follow_barrels`, also the files that import a name the node defines through re-exporting files (FR-010)."""
    _check_limit(limit)
    node = resolve(ix, target)
    g = _links(ix, include_type_only)
    found = {}
    for dep in g.predecessors(node):
        edges = g.edges[dep, node]["edges"]
        if symbol is not None:
            edges = tuple(e for e in edges if _matches(e, symbol))
            if not edges:
                continue
        found[dep] = _make_link(dep, node, edges)
    if follow_barrels:
        for (dep, defining), link in _barrel_links(ix, include_type_only, symbol).items():
            if defining == node and dep not in found:
                found[dep] = link
    items = [_item(dep, (found[dep],)) for dep in sorted(found)]
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
    _check_limit(limit)
    _check_depth(max_depth)
    node = resolve(ix, target)
    g = _links(ix, include_type_only)
    barrels = _barrel_links(ix, include_type_only) if follow_barrels else {}
    barrel_preds: dict[str, set[str]] = defaultdict(set)
    barrel_succs: dict[str, set[str]] = defaultdict(set)
    for dep, defining in barrels:
        barrel_preds[defining].add(dep)
        barrel_succs[dep].add(defining)

    def preds(n: str) -> set[str]:
        return set(g.predecessors(n)) | barrel_preds[n] if n in g else barrel_preds[n]

    distance = {node: 0}
    level = [node]
    depth = 0
    while level and (max_depth is None or depth < max_depth):
        depth += 1
        level = sorted({dep for n in level for dep in preds(n) if dep not in distance})
        for dep in level:
            distance[dep] = depth
    cut = max_depth is not None and any(dep not in distance for n in level for dep in preds(n))

    def next_hop(n: str) -> str:
        succs = set(g.successors(n)) | barrel_succs[n]
        return min(s for s in succs if distance.get(s) == distance[n] - 1)

    def link(a: str, b: str) -> Link:
        return ix.link(a, b, include_type_only) if g.has_edge(a, b) else barrels[(a, b)]

    items = []
    for dep in sorted((n for n in distance if n != node), key=lambda n: (distance[n], n)):
        chain = []
        current = dep
        while current != node:
            hop = next_hop(current)
            chain.append(link(current, hop))
            current = hop
        items.append(_item(dep, tuple(chain), distance[dep]))
    options = {"follow_barrels": follow_barrels, "include_type_only": include_type_only, "limit": limit, "max_depth": max_depth}
    return _answer(ix, "impact", node, options, items, limit, cut=cut)


def _defines(node: FileNode, name: str) -> bool:
    return any(name in (d.exported_as or ()) for d in node.definitions) or any(x.name == name for x in node.exports or ())


def _trace(
    ix: GraphIndex, reexports: dict[str, list[Edge]], file_id: str, name: str, seen: frozenset[str]
) -> tuple[str, tuple[Edge, ...]] | None:
    """Where `name`, as exported by `file_id`, is defined, and the re-export edges that lead there (research § R8).
    Only TS/JS files are followed (Python files carry no export records); a file already on the path stops it."""
    node = ix.nodes.get(file_id)
    if not isinstance(node, FileNode) or node.exports is None:
        return None
    if _defines(node, name):
        return file_id, ()
    seen = seen | {file_id}
    for r in reexports.get(file_id, ()):
        if r.target in seen:
            continue
        if r.symbol == "*" and r.alias == name:  # export * as name from "./x": the whole module
            return r.target, (r,)
        if r.symbol != "*" and (r.alias or r.symbol) == name:
            found = _trace(ix, reexports, r.target, r.symbol, seen)
            if found is not None:
                return found[0], (r,) + found[1]
    for r in reexports.get(file_id, ()):
        if r.symbol == "*" and r.alias is None and r.target not in seen:
            found = _trace(ix, reexports, r.target, name, seen)
            if found is not None:
                return found[0], (r,) + found[1]
    return None


def _barrel_links(ix: GraphIndex, include_type_only: bool, symbol: str | None = None) -> dict[tuple[str, str], Link]:
    """Derived links (importer, defining file) for names imported from re-exporting files. `edges` are the
    import edges, `via` the re-export edges of the first of them; a pair already linked directly is left out."""
    if symbol is None and include_type_only in ix._barrels:
        return ix._barrels[include_type_only]
    kept = [e for e in sorted(ix.doc.edges, key=edge_sort_key) if e.confidence != "unresolved" and (include_type_only or not e.type_only)]
    reexports: dict[str, list[Edge]] = defaultdict(list)
    for e in kept:
        if e.type == "reexports" and e.target.startswith("file:"):
            reexports[e.source].append(e)

    found: dict[tuple[str, str], tuple[list[Edge], tuple[Edge, ...]]] = {}
    for e in kept:
        if e.type != "imports" or e.symbol in (None, "*") or (symbol is not None and e.symbol != symbol):
            continue
        traced = _trace(ix, reexports, e.target, e.symbol, frozenset())
        if traced is None or traced[0] in (e.target, e.source):
            continue
        pair = (e.source, traced[0])
        if pair not in found:
            found[pair] = ([], traced[1])
        found[pair][0].append(e)

    direct = _links(ix, include_type_only)
    out = {}
    for pair in sorted(found):
        if direct.has_edge(*pair):
            continue
        edges, via = tuple(found[pair][0]), found[pair][1]
        out[pair] = Link(
            source=pair[0],
            target=pair[1],
            edges=edges,
            confidence=weakest([strongest(e.confidence for e in edges)] + [v.confidence for v in via]),
            type_only=all(e.type_only for e in edges) or any(v.type_only for v in via),
            via=via,
        )
    if symbol is None:
        ix._barrels[include_type_only] = out
    return out


def _loops(g: nx.DiGraph) -> list[tuple[str, ...]]:
    """Groups of files in a loop: components of two or more files, and single files that import themselves."""
    groups = []
    for component in nx.strongly_connected_components(g):
        files = tuple(sorted(component))
        if len(files) > 1 or g.has_edge(files[0], files[0]):
            groups.append(files)
    return sorted(groups)


def _shortest_cycle(g: nx.DiGraph, start: str, members: set[str]) -> list[str]:
    """Nodes of the shortest cycle through `start`, inside the group, by breadth-first search with neighbours in
    id order; the first node found that links back to `start` closes it (research § R6)."""
    if g.has_edge(start, start):
        return [start]
    parent = {start: start}
    queue = [start]
    for current in queue:
        for nxt in sorted(g.successors(current)):
            if nxt not in members or nxt in parent:
                continue
            parent[nxt] = current
            if g.has_edge(nxt, start):
                path = [nxt]
                while path[-1] != start:
                    path.append(parent[path[-1]])
                return path[::-1]
            queue.append(nxt)
    raise AssertionError(f"{start} is in a loop but no cycle was found")


def cycles(ix: GraphIndex, *, include_type_only: bool = True, limit: int | None = None) -> Answer:
    """Every group of files that depend on each other in a loop, with one example cycle each (FR-008)."""
    _check_limit(limit)
    links = _links(ix, include_type_only)
    files = links.subgraph(n for n in links.nodes if n.startswith("file:"))
    runtime = _links(ix, include_type_only=False)
    groups = []
    for members in _loops(files):
        path = _shortest_cycle(files, members[0], set(members))
        cycle = tuple(ix.link(a, b, include_type_only) for a, b in zip(path, path[1:] + path[:1], strict=True))
        groups.append(
            CycleGroup(
                files=members,
                cycle=cycle,
                type_only=not _loops(runtime.subgraph(members)),
                confidence=weakest(link.confidence for link in cycle),
            )
        )
    shown, total, truncated = _limit(groups, limit)
    return Answer(
        snapshot=ix.doc.snapshot,
        question="cycles",
        target=None,
        options={"include_type_only": include_type_only, "limit": limit},
        total=total,
        truncated=truncated,
        groups=tuple(shown),
    )


def neighbors(ix: GraphIndex, target: str, *, include_type_only: bool = True, limit: int | None = None) -> Answer:
    """What the node imports and what imports it, together (FR-007). The limit cuts each list on its own."""
    _check_limit(limit)
    out = dependencies(ix, target, include_type_only=include_type_only)
    into = dependents(ix, target, include_type_only=include_type_only)
    outgoing, out_total, out_cut = _limit(list(out.items or ()), limit)
    incoming, in_total, in_cut = _limit(list(into.items or ()), limit)
    return Answer(
        snapshot=ix.doc.snapshot,
        question="neighbors",
        target=out.target,
        options={"include_type_only": include_type_only, "limit": limit},
        total=out_total + in_total,
        truncated=out_cut or in_cut,
        outgoing=tuple(outgoing),
        incoming=tuple(incoming),
        unresolved=out.unresolved,
        completeness=ix.completeness,
    )


def key_files(ix: GraphIndex, *, include_type_only: bool = True, limit: int | None = 10) -> Answer:
    """Project files ranked by transitive dependents, then direct dependents, then path (FR-009, research § R7).

    Each file's dependents are counted once on the condensation (every loop squeezed into one node), walked in
    topological order; sets of files are Python ints used as bitsets, one bit per file in id order. Files in one
    loop share the set and never count themselves."""
    _check_limit(limit)
    links = _links(ix, include_type_only)
    files = links.subgraph(n for n in links.nodes if n.startswith("file:"))
    bit = {f: 1 << i for i, f in enumerate(sorted(files.nodes))}
    dag = nx.condensation(files)
    members = {c: sum(bit[f] for f in dag.nodes[c]["members"]) for c in dag.nodes}
    reach: dict[int, int] = {}
    for c in nx.topological_sort(dag):
        reach[c] = 0
        for p in dag.predecessors(c):
            reach[c] |= reach[p] | members[p]

    items = []
    for f in files.nodes:
        component = dag.graph["mapping"][f]
        transitive = ((reach[component] | members[component]) & ~bit[f]).bit_count()
        if transitive == 0:
            continue
        direct = sum(1 for p in files.predecessors(f) if p != f)
        items.append(Item(node=f, kind="file", transitive_dependents=transitive, direct_dependents=direct))
    items.sort(key=lambda i: (-(i.transitive_dependents or 0), -(i.direct_dependents or 0), i.node))
    return _answer(ix, "key_files", None, {"include_type_only": include_type_only, "limit": limit}, items, limit)


def overview(ix: GraphIndex) -> Overview:
    """What the graph covers: languages, file statuses, node kinds and unresolved imports (006 research § R9)."""
    doc = ix.doc
    statuses = Counter(f.status for f in doc.files)
    kinds = Counter(type(n) for n in ix.nodes.values())
    return Overview(
        snapshot=doc.snapshot,
        schema_version=SCHEMA_VERSION,
        extractors=dict(sorted(doc.extractors.items())),
        languages=dict(sorted(Counter(f.language for f in doc.files if f.language is not None).items())),
        files={
            "analyzed": statuses["analyzed"],
            "detected_only": statuses["detected_only"],
            "not_code": statuses["not_code"],
            "skipped": len(doc.skipped),
        },
        nodes={
            "file": kinds[FileNode],
            "external": kinds[ExternalNode],
            "unresolved": kinds[UnresolvedNode],
            "asset": kinds[AssetNode],
        },
        edges=len(doc.edges),
        unresolved_imports=ix.completeness.unresolved_imports,
    )
