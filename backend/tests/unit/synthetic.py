"""Small synthetic graph documents for query tests (specs/004-graph-queries tasks T006, T008)."""

from graphora.graph.model import AssetNode, CoverageFile, Edge, ExternalNode, FileNode, GraphDocument, ProjectNode, UnresolvedNode

SNAP = "content:0123456789abcdef"


def edge(source, target, line=1, *, column=1, symbol=None, confidence="resolved", reason=None, **extra):
    """`source`/`target` are paths or ids; plain paths become `file:` ids."""
    src = source if ":" in source else f"file:{source}"
    dst = target if ":" in target else f"file:{target}"
    if dst.startswith("unresolved:"):
        confidence, reason = "unresolved", reason or "not_found"
    elif confidence == "heuristic":
        reason = reason or "namespace_spread"  # v4: a heuristic edge carries a reason
    return Edge(src, dst, symbol, line, column, SNAP, confidence, reason, "python-adapter@0.2.0", "sha256:0000000000000000", **extra)


def _node(node_id: str):
    kind, _, rest = node_id.partition(":")
    if kind == "file":
        if rest.endswith((".ts", ".tsx")):
            return FileNode(rest, "typescript", (), ())
        if rest.endswith(".cs"):
            return FileNode(rest, "csharp")
        return FileNode(rest, "python")
    if kind == "ext":
        ecosystem, _, name = rest.partition(":")
        return ExternalNode(name, ecosystem, "third_party")
    if kind == "unresolved":
        ecosystem, _, ref = rest.partition(":")
        return UnresolvedNode(ref, ecosystem)
    if kind == "project":
        return ProjectNode(rest)
    return AssetNode(rest)


def make_doc(edges, files=(), coverage=(), skipped=(), nodes=()):
    """A synthetic document: nodes for every edge end and every extra file path; coverage defaults to analyzed.
    `nodes` replaces the generated node of the same id (to give a file definitions or exports)."""
    given = {n.id: n for n in nodes}
    ids = {e.source for e in edges} | {e.target for e in edges} | {f"file:{p}" for p in files} | set(given)
    nodes = tuple(given.get(i) or _node(i) for i in sorted(ids))
    covered = {c.path for c in coverage}
    analyzed = tuple(
        CoverageFile(n.path, n.language, "analyzed") for n in nodes if isinstance(n, FileNode) and n.path not in covered
    )
    return GraphDocument(SNAP, {"python-adapter": "0.2.0"}, nodes, tuple(edges), analyzed + tuple(coverage), tuple(skipped))
