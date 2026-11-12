"""The overview query (specs/006-mcp-server research § R9, data-model.md § Overview)."""

import json

from conftest import analyzed_graph
from graphora.graph.load import loads
from graphora.graph.model import CoverageFile, Skipped
from graphora.graph.queries import index, overview
from graphora.graph.results import dumps, render_text
from synthetic import SNAP, edge, make_doc


def test_counts_on_a_synthetic_graph():
    doc = make_doc(
        [edge("a.py", "b.py"), edge("a.py", "ext:python:yaml"), edge("b.py", "unresolved:python:gone", 4)],
        coverage=[CoverageFile("tool.go", "go", "detected_only"), CoverageFile("README.md", None, "not_code")],
        skipped=[Skipped("node_modules", "excluded_dir")],
    )
    o = overview(index(doc))
    assert o.to_dict() == {
        "snapshot": SNAP,
        "schema_version": 6,
        "extractors": {"python-adapter": "0.2.0"},
        "languages": {"go": 1, "python": 2},
        "files": {"analyzed": 2, "detected_only": 1, "not_code": 1, "skipped": 1},
        "nodes": {"file": 2, "external": 1, "unresolved": 1, "asset": 0, "project": 0, "solution": 0},
        "edges": 3,
        "unresolved_imports": 1,
    }


def test_matches_the_coverage_summary_of_a_fixture():
    data = analyzed_graph("py-dynamic")
    doc = json.loads(data)
    o = overview(index(loads(data)))
    summary = doc["coverage"]["summary"]
    assert o.languages == summary["by_language"]
    assert o.files == {k: summary[k] for k in ("analyzed", "detected_only", "not_code", "skipped")}
    assert sum(o.nodes.values()) == len(doc["nodes"])
    assert o.edges == len(doc["edges"])
    assert o.unresolved_imports == sum(1 for e in doc["edges"] if e["confidence"] == "unresolved")
    assert o.snapshot == doc["snapshot"]


def test_same_bytes_twice():
    ix = index(loads(analyzed_graph("py-dynamic")))
    assert dumps(overview(ix)) == dumps(overview(ix))


def test_text():
    text = render_text(overview(index(make_doc([edge("a.py", "b.py")]))))
    assert text.startswith(f"overview @ {SNAP}\n")
    assert "files: 2 analyzed, 0 detected only, 0 not code, 0 skipped" in text
    assert "edges: 1 (0 unresolved imports)" in text


def test_counts_csharp_projects():
    """007: project nodes are counted, and every node kind is covered by the counts."""
    data = analyzed_graph("csharp-multiproject")
    o = overview(index(loads(data)))
    assert (o.nodes["project"], o.nodes["solution"]) == (7, 2)  # 009 added LoopA, LoopB and two solutions
    assert sum(o.nodes.values()) == len(json.loads(data)["nodes"])
