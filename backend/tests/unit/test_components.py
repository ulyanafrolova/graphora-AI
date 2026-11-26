"""Components of a snapshot: Louvain with a fixed seed, folder names (specs/019-frontend research § R3)."""

import json

from graphora.graph import queries
from graphora.graph.model import CoverageFile, Edge, ExternalNode, FileNode, GraphDocument, UnresolvedNode
from graphora.graph.results import dumps

SNAP = "content:0123456789abcdef"


def edge(source, target, line=1, **kw):
    kw.setdefault("confidence", "resolved")
    kw.setdefault("reason", None)
    src = f"file:{source}"
    tgt = target if ":" in target else f"file:{target}"
    return Edge(src, tgt, None, line, 1, SNAP, extractor="python-adapter@0.2.0", snippet_hash="sha256:0000000000000000", **kw)


def doc(edges, files=(), externals=(), unresolved=()):
    linked = {e.source.removeprefix("file:") for e in edges}
    linked |= {e.target.removeprefix("file:") for e in edges if e.target.startswith("file:")}
    paths = sorted(linked | set(files))
    nodes = tuple(FileNode(p, "typescript" if p.endswith(".ts") else "python") for p in paths)
    nodes += tuple(ExternalNode(n, "python", "third_party") for n in externals)
    nodes += tuple(UnresolvedNode(r, "python") for r in unresolved)
    coverage = tuple(CoverageFile(p, "typescript" if p.endswith(".ts") else "python", "analyzed") for p in paths)
    return GraphDocument(SNAP, {"python-adapter": "0.2.0"}, nodes, tuple(edges), coverage, ())


def answer(d, **options):
    return json.loads(dumps(queries.components(queries.index(d), **options)))


def short(a):
    return [(c["id"], c["name"], [f.removeprefix("file:") for f in c["files"]], c["has_cycle"]) for c in a["components"]]


CLUSTERS = [
    edge("a/x1.py", "a/x2.py"),
    edge("a/x2.py", "a/x3.py"),
    edge("a/x3.py", "a/x1.py"),
    edge("a/x1.py", "a/x3.py", line=2),
    edge("b/y1.py", "b/y2.py"),
    edge("b/y2.py", "b/y3.py"),
    edge("b/y1.py", "b/y3.py", line=2),
    edge("a/x1.py", "b/y1.py", line=3),
]


def test_two_clusters():
    a = answer(doc(CLUSTERS))
    assert short(a) == [
        ("component:1", "a", ["a/x1.py", "a/x2.py", "a/x3.py"], True),
        ("component:2", "b", ["b/y1.py", "b/y2.py", "b/y3.py"], False),
    ]
    assert [c["file_count"] for c in a["components"]] == [3, 3]
    assert a["links"] == [{"source": "component:1", "target": "component:2", "imports": 1, "heuristic": 0, "in_cycle": False}]
    assert (a["question"], a["target"], a["options"], a["total"], a["truncated"]) == (
        "components",
        None,
        {"include_type_only": True},
        2,
        False,
    )


def test_same_bytes_twice():
    d = doc(CLUSTERS)
    assert dumps(queries.components(queries.index(d))) == dumps(queries.components(queries.index(d)))


def test_isolated_files():
    d = doc([edge("a/1.py", "a/2.py")], files=["a/__init__.py", "a/sub/3.py", "tools/x.py", "tools/y.py", "z.py"])
    assert short(answer(d)) == [
        ("component:1", "a", ["a/1.py", "a/2.py", "a/__init__.py", "a/sub/3.py"], False),
        ("component:2", "tools", ["tools/x.py", "tools/y.py"], False),
        ("component:3", ".", ["z.py"], False),
    ]
    assert answer(d)["links"] == []


def test_self_import_does_not_link():
    d = doc([edge("a/1.py", "a/2.py"), edge("b/s.py", "b/s.py")])
    assert short(answer(d)) == [
        ("component:1", "a", ["a/1.py", "a/2.py"], False),
        ("component:2", "b", ["b/s.py"], True),
    ]


def test_externals_and_unresolved_left_out():
    edges = CLUSTERS + [
        edge("a/x1.py", "ext:python:requests", line=4),
        edge("b/y1.py", "unresolved:python:gone", line=4, confidence="unresolved", reason="not_found"),
    ]
    a = answer(doc(edges, externals=["requests"], unresolved=["gone"]))
    files = [f for c in a["components"] for f in c["files"]]
    assert all(f.startswith("file:") for f in files) and len(files) == 6
    assert len(a["links"]) == 1


def test_heuristic_links_counted():
    http = Edge(
        "file:b/y1.py",
        "file:a/x2.py",
        None,
        5,
        1,
        SNAP,
        "heuristic",
        "http_route",
        "python-adapter@0.2.0",
        "sha256:0000000000000000",
        type="http_call",
        route_line=1,
    )
    a = answer(doc(CLUSTERS[:-1] + [http]))
    assert a["links"] == [{"source": "component:2", "target": "component:1", "imports": 1, "heuristic": 1, "in_cycle": False}]


def test_cycle_between_components():
    edges = CLUSTERS + [edge("b/y1.py", "a/x1.py", line=5)]
    a = answer(doc(edges))
    assert [(link["source"], link["target"], link["in_cycle"]) for link in a["links"]] == [
        ("component:1", "component:2", True),
        ("component:2", "component:1", True),
    ]


def test_type_only_links():
    edges = CLUSTERS[:-1] + [edge("a/x1.py", "b/y1.py", line=3, type_only=True)]
    assert len(answer(doc(edges))["links"]) == 1
    assert answer(doc(edges), include_type_only=False)["links"] == []


def test_names():
    names = queries._component_names
    assert names([["src/auth/a.py", "src/auth/b.py"]]) == ["src/auth"]
    assert names([["src/auth/a.py", "src/users/b.py"]]) == ["src"]
    assert names([["api/x.py", "web/y.py", "web/z.py"]]) == ["web"]
    assert names([["api/x.py", "web/y.py"]]) == ["api"]
    assert names([["a.py", "b.py"]]) == ["."]
    assert names([["a.py", "web/b.py"]]) == ["."]
    assert names([["src/a/1.py", "src/b/2.py"], ["src/c/3.py", "src/d/4.py"], ["src/e/5.py", "src/f/6.py"]]) == [
        "src",
        "src · 2",
        "src · 3",
    ]
    assert names([["web/a.py"], ["web/b.py"], ["api/c.py"]]) == ["web", "web · 2", "api"]
