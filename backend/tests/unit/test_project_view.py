"""Project-level view (specs/009-csharp-solutions-project-views research § R4)."""

from graphora.graph.model import FileNode
from graphora.graph.project_view import ProjectView
from graphora.graph.queries import index
from synthetic import edge, make_doc

A, B, C = "project:a/A.csproj", "project:b/B.csproj", "project:c/C.csproj"


def _file(path, project):
    return FileNode(path, "csharp", (), None, project)


FILES = (
    _file("a/X.cs", A),
    _file("a/Y.cs", A),
    _file("b/Z.cs", B),
    _file("c/W.cs", C),
    _file("loose/L.cs", None),
)


def _view(edges):
    ix = index(make_doc(edges, nodes=FILES))
    return ProjectView(ix.nodes, ix.doc.edges)


def test_evidence_from_code_edges_between_projects():
    e1 = edge("a/Y.cs", "b/Z.cs", 3, type="type_reference")
    e2 = edge("a/X.cs", "b/Z.cs", 7)
    inside = edge("a/X.cs", "a/Y.cs", 2, type="type_reference")
    loose = edge("loose/L.cs", "b/Z.cs", 1)
    v = _view([e1, e2, inside, loose])
    assert list(v.links) == [(A, B)]
    assert v.links[(A, B)].evidence == (e2, e1)  # sorted by source path, then line
    assert v.links[(A, B)].confidence == "resolved"
    assert not v.links[(A, B)].declared_only


def test_declared_only_and_declared_with_evidence():
    ref_b = edge(A, B, 4, type="project_reference")
    ref_c = edge(A, C, 5, type="project_reference")
    use_b = edge("a/X.cs", "b/Z.cs", 9, type="type_reference")
    v = _view([ref_b, ref_c, use_b])
    assert v.links[(A, B)].declared == (ref_b,) and v.links[(A, B)].evidence == (use_b,)
    assert v.links[(A, C)].declared_only and v.links[(A, C)].declared == (ref_c,)
    assert list(v.code_graph.edges) == [(A, B)]
    assert sorted(v.graph.edges) == [(A, B), (A, C)]


def test_heuristic_only_link_and_unresolved_ignored():
    h = edge("a/X.cs", "b/Z.cs", 1, confidence="heuristic", reason="namespace_spread")
    u = edge("a/X.cs", "unresolved:dotnet:Gone", 2)
    v = _view([h, u])
    assert v.links[(A, B)].confidence == "heuristic"
    assert list(v.links) == [(A, B)]


def test_packages_from_declared_and_code_edges_and_dotnet_ignored():
    declared = edge(A, "ext:nuget:Serilog", 6, type="package_reference")
    used = edge("a/X.cs", "ext:nuget:Serilog", 2, confidence="heuristic", reason="package_prefix")
    bcl = edge("a/X.cs", "ext:dotnet:System.Linq", 1)
    v = _view([declared, used, bcl])
    assert list(v.links) == [(A, "ext:nuget:Serilog")]
    link = v.links[(A, "ext:nuget:Serilog")]
    assert (link.evidence, link.declared, link.confidence) == ((used,), (declared,), "heuristic")
    assert list(v.code_graph.edges) == []  # packages are not projects


def test_files_of_and_determinism():
    edges = [edge("c/W.cs", "a/X.cs", 1), edge("a/X.cs", "b/Z.cs", 1), edge("b/Z.cs", "c/W.cs", 1)]
    v1, v2 = _view(edges), _view(list(reversed(edges)))
    assert list(v1.links) == list(v2.links) == [(A, B), (B, C), (C, A)]
    assert v1.files_of(A) == ("file:a/X.cs", "file:a/Y.cs")
    assert v1.files_of(None) == ("file:loose/L.cs",)
