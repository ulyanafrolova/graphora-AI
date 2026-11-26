"""Reading a graph document back (specs/004-graph-queries research § R2)."""

import hashlib
import json

import pytest

from conftest import FIXTURES, analyzed_graph
from graphora.graph import serialize
from graphora.graph.load import InvalidGraph, loads

FIXTURE_NAMES = sorted(p.name for p in FIXTURES.iterdir() if (p / "expected.json").is_file())


def _doc() -> dict:
    return json.loads(analyzed_graph("py-flat"))


def _bytes(doc: dict) -> bytes:
    return json.dumps(doc).encode("utf-8")


def _first(doc: dict, kind: str) -> dict:
    return next(n for n in doc["nodes"] if n["kind"] == kind)


def _rehash(edge: dict) -> None:
    """Recompute the edge id after changing a field, so only the intended check fails."""
    key = (edge["source"], edge["line"], edge["column"], edge["target"], edge["symbol"] or "", edge.get("alias") or "", edge["type"])
    edge["id"] = "e:" + hashlib.sha256("|".join(str(p) for p in key).encode()).hexdigest()[:16]


def _resolved_edge(doc: dict) -> dict:
    return next(e for e in doc["edges"] if e["confidence"] == "resolved")


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_round_trip(name):
    data = analyzed_graph(name)
    assert serialize.dumps(loads(data)) == data


def _invalid(data: bytes, *words: str) -> None:
    with pytest.raises(InvalidGraph) as exc:
        loads(data)
    for word in words:
        assert word in exc.value.message


def test_not_json():
    _invalid(b"{not json", "JSON")


def test_not_an_object():
    _invalid(b"[1, 2]", "object")


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 6, 7, 9])
def test_schema_version(version):
    doc = _doc()
    doc["schema_version"] = version
    _invalid(_bytes(doc), "schema_version", str(version))


def test_missing_node_field():
    doc = _doc()
    del _first(doc, "file")["path"]
    _invalid(_bytes(doc), "path")


def test_missing_edge_field():
    doc = _doc()
    del doc["edges"][0]["line"]
    _invalid(_bytes(doc), "line")


def test_unknown_confidence():
    doc = _doc()
    _resolved_edge(doc)["confidence"] = "guess"
    _invalid(_bytes(doc), "guess")


def test_unknown_edge_type():
    doc = _doc()
    doc["edges"][0]["type"] = "calls"
    _invalid(_bytes(doc), "calls")


def test_edge_snapshot_differs():
    doc = _doc()
    doc["edges"][0]["snapshot"] = "content:ffffffffffffffff"
    _invalid(_bytes(doc), "snapshot")


def test_edge_source_not_a_node():
    doc = _doc()
    doc["edges"][0]["source"] = "file:missing.py"
    _rehash(doc["edges"][0])
    _invalid(_bytes(doc), "file:missing.py")


def test_edge_target_not_a_node():
    doc = _doc()
    edge = _resolved_edge(doc)
    edge["target"] = "file:missing.py"
    _rehash(edge)
    _invalid(_bytes(doc), "file:missing.py")


def test_edge_id_differs():
    doc = _doc()
    doc["edges"][0]["id"] = "e:0000000000000000"
    _invalid(_bytes(doc), "e:0000000000000000")


def test_unresolved_without_reason():
    doc = _doc()
    edge = next(e for e in doc["edges"] if e["confidence"] == "unresolved")
    del edge["reason"]
    _invalid(_bytes(doc), "reason")


# --- v4: C# documents (specs/007-csharp-analysis/data-model.md) -------------------------------------------------


def _cs_bytes(**edge_changes) -> bytes:
    from graphora.graph.model import CoverageFile, Definition, Edge, FileNode, GraphDocument, ProjectNode

    snap = "content:0123456789abcdef"
    h = "sha256:0000000000000000"
    edge = Edge("project:A/A.csproj", "project:B/B.csproj", "..\\B\\B.csproj", 3, 5, snap, "resolved", None, "csproj-reader@0.1.0", h, type="project_reference")
    using = Edge("file:A/P.cs", "file:B/Q.cs", "B", 1, 1, snap, "heuristic", "namespace_spread", "csharp-adapter@0.1.0", h, directive="using", global_using=True)
    doc = serialize.to_dict(
        GraphDocument(
            snap,
            {"csharp-adapter": "0.1.0"},
            (
                FileNode("A/P.cs", "csharp", (Definition("struct", "A.S", 2),), None, "project:A/A.csproj"),
                FileNode("B/Q.cs", "csharp", (), None, None),
                ProjectNode("A/A.csproj"),
                ProjectNode("B/B.csproj"),
            ),
            (edge, using),
            (CoverageFile("A/P.cs", "csharp", "analyzed", ("ambiguous_project",), 2),),
            (),
        )
    )
    for e in doc["edges"]:
        if e["type"] == "project_reference":
            e.update(edge_changes)
            _rehash(e)
    return _bytes(doc)


def test_csharp_round_trip():
    data = serialize.dumps(loads(_cs_bytes()))
    assert loads(data) == loads(_cs_bytes())
    assert serialize.dumps(loads(data)) == data


def test_project_edge_from_file_rejected():
    _invalid(_cs_bytes(source="file:A/P.cs"), "not a project node")


def test_solution_round_trip_and_source_check():
    from graphora.graph.model import Edge, GraphDocument, ProjectNode, SolutionNode

    snap, h = "content:0123456789abcdef", "sha256:0000000000000000"
    member = Edge("solution:A.sln", "project:A/A.csproj", "A\\A.csproj", 5, 1, snap, "resolved", None, "sln-reader@0.1.0", h, type="solution_member")
    doc = serialize.to_dict(GraphDocument(snap, {}, (SolutionNode("A.sln"), ProjectNode("A/A.csproj")), (member,), (), ()))
    data = _bytes(doc)
    assert serialize.dumps(loads(data)) == serialize.dumps(loads(serialize.dumps(loads(data))))
    doc["edges"][0]["source"] = "project:A/A.csproj"
    _rehash(doc["edges"][0])
    _invalid(_bytes(doc), "not a solution node")


SHA = "c" * 40


def _history_doc() -> dict:
    """py-flat moved to a commit snapshot, with an available history over two of its files."""
    doc = _doc()
    doc["snapshot"] = SHA
    for e in doc["edges"]:
        e["snapshot"] = SHA
    doc["history"].update(
        status="available",
        reason=None,
        commit=SHA,
        window_start="2025-01-01T00:00:00Z",
        newest="2026-01-01T00:00:00Z",
        oldest="2025-02-01T00:00:00Z",
        commits_read=4,
        files=[{"path": "main.py", "commits": 3, "authors": 2}, {"path": "pkg/a.py", "commits": 1, "authors": 1}],
    )
    return doc


def test_history_round_trip():
    data = serialize.dumps(loads(_bytes(_history_doc())))
    assert serialize.dumps(loads(data)) == data
    assert loads(data).history.files[0].commits == 3


def test_history_missing():
    doc = _doc()
    del doc["history"]
    _invalid(_bytes(doc), "history")


@pytest.mark.parametrize(
    ("field", "value", "word"),
    [
        ("status", "done", "done"),
        ("reason", "lost", "lost"),
        ("commits_read", "4", "commits_read"),
        ("local_changes", 0, "local_changes"),
    ],
)
def test_history_field_values(field, value, word):
    doc = _history_doc()
    if field == "reason":
        doc["history"].update(status="not_available", commit=None, window_start=None, newest=None, oldest=None,
                              commits_read=0, files=[])
    doc["history"][field] = value
    _invalid(_bytes(doc), word)


def test_history_rule_broken():
    doc = _history_doc()
    doc["history"]["reason"] = "zip"
    _invalid(_bytes(doc), "history")


def test_history_files_unsorted():
    doc = _history_doc()
    doc["history"]["files"].reverse()
    _invalid(_bytes(doc), "sorted")


def test_history_file_not_a_node():
    doc = _history_doc()
    doc["history"]["files"][0]["path"] = "README.md"
    _invalid(_bytes(doc), "README.md")


def test_history_authors_over_commits():
    doc = _history_doc()
    doc["history"]["files"][1]["authors"] = 2
    _invalid(_bytes(doc), "authors")


def test_history_commit_differs_from_snapshot():
    doc = _history_doc()
    doc["history"]["commit"] = "d" * 40
    _invalid(_bytes(doc), "commit")


def test_history_commit_of_dirty_snapshot():
    doc = _history_doc()
    doc["snapshot"] = SHA + "+dirty:0123456789abcdef"
    for e in doc["edges"]:
        e["snapshot"] = doc["snapshot"]
    doc["history"]["local_changes"] = True
    assert loads(_bytes(doc)).history.local_changes
