"""Project-level view (specs/009-csharp-solutions-project-views research § R4)."""

import pytest

from graphora.graph.model import FileNode
from graphora.graph.project_view import ProjectView
from graphora.graph.queries import NodeNotFound, cycles, dependencies, dependents, impact, index
from graphora.graph.results import render_text
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


# --- project-level questions (research § R5) ---------------------------------------------------------------------


def _ix(edges):
    return index(make_doc(edges, nodes=FILES))


EDGES = [
    edge(A, B, 4, type="project_reference"),
    edge(A, C, 5, type="project_reference"),
    edge(A, "unresolved:dotnet:Missing.csproj", 6, type="project_reference", reason="not_found"),
    edge("a/X.cs", "b/Z.cs", 3, type="type_reference", symbol="B.Z"),
    edge("a/Y.cs", "b/Z.cs", 8, type="type_reference", symbol="B.Z"),
    edge("b/Z.cs", "c/W.cs", 2, type="type_reference", symbol="C.W"),
    edge("c/W.cs", "b/Z.cs", 9, confidence="heuristic", reason="namespace_spread"),
]


def test_project_dependencies_with_evidence_and_declared_only():
    answer = dependencies(_ix(EDGES), "a/A.csproj", level="project")
    assert [(i.node, i.declared_only, len(i.chain[0].edges), len(i.chain[0].declared)) for i in answer.items] == [
        (B, False, 2, 1),
        (C, True, 1, 1),
    ]
    assert [e.target for e in answer.unresolved] == ["unresolved:dotnet:Missing.csproj"]
    text = render_text(answer)
    assert "b/B.csproj  a/X.cs:3 (+1 more) → b/B.csproj" in text
    assert "c/C.csproj  a/A.csproj:5 → c/C.csproj (declared, not used by code)" in text


def test_project_dependents_from_a_file_target():
    answer = dependents(_ix(EDGES), "c/W.cs", level="project")  # a C# file stands for its project
    assert answer.target == C
    assert [(i.node, i.confidence, i.declared_only) for i in answer.items] == [(A, "resolved", True), (B, "resolved", False)]


def test_project_impact_uses_code_links_only():
    answer = impact(_ix(EDGES), "c/C.csproj", level="project")
    assert [(i.node, i.distance) for i in answer.items] == [(B, 1), (A, 2)]  # A reaches C only through B in code
    assert [link.target for link in answer.items[1].chain] == [B, C]


def test_project_cycles():
    answer = cycles(_ix(EDGES), level="project")
    (group,) = answer.groups
    assert group.files == (B, C)
    assert group.confidence == "heuristic"  # B → C resolved, C → B heuristic: a cycle is only as sure as its weakest link
    assert [link.confidence for link in group.cycle] == ["resolved", "heuristic"]


def test_project_level_errors():
    ix = _ix(EDGES)
    with pytest.raises(NodeNotFound) as exc:
        dependencies(ix, "loose/L.cs", level="project")
    assert exc.value.status == "not_a_project"
    for kwargs in ({"symbol": "X"}, {"follow_barrels": True}, {"include_type_only": False}):
        with pytest.raises(ValueError):
            dependents(ix, "b/B.csproj", level="project", **kwargs)
    with pytest.raises(ValueError):
        cycles(ix, level="module")


def test_no_projects_gives_empty_answers():
    ix = index(make_doc([edge("a.py", "b.py")]))
    assert cycles(ix, level="project").groups == ()


# --- projects question (research § R6) --------------------------------------------------------------------------


def test_projects_summary_and_no_project_entry():
    from graphora.graph.queries import projects

    member = edge("solution:All.sln", A, 3, type="solution_member")
    missing = edge("solution:All.sln", "unresolved:dotnet:z/Z.csproj", 5, type="solution_member", reason="not_found")
    answer = projects(_ix([*EDGES, member, missing]))
    by_id = {p.project: p for p in answer.projects}
    assert [p.project for p in answer.projects] == [A, B, C, None]
    assert (by_id[A].solutions, by_id[A].references, by_id[A].uses, by_id[A].files) == (("solution:All.sln",), (B, C), (B,), 2)
    assert (by_id[B].uses, by_id[B].used_by) == ((C,), (A, C))
    assert (by_id[None].path, by_id[None].files) == (None, 1)
    text = render_text(answer)
    assert "a/A.csproj  2 files  in All.sln" in text and "(no project)  1 files" in text
    assert "  uses: b/B.csproj" in text


def test_projects_empty_without_csharp():
    from graphora.graph.queries import projects

    answer = projects(index(make_doc([edge("a.py", "b.py")])))
    assert (answer.projects, answer.total) == ((), 0)
