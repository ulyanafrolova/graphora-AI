import hashlib
import json

from graphora.graph.model import (
    CoverageFile,
    Definition,
    Edge,
    ExternalNode,
    FileNode,
    GraphDocument,
    Skipped,
    UnresolvedNode,
)
from graphora.graph.serialize import dumps, edge_id, to_dict

SNAP = "content:0123456789abcdef"


def _edge(source, target, line, column=1, symbol=None, confidence="resolved", reason=None):
    return Edge(source, target, symbol, line, column, SNAP, confidence, reason, "python-adapter@0.1.0", "sha256:0000000000000000")


def _doc():
    return GraphDocument(
        snapshot=SNAP,
        extractors={"python-resolver": "0.1.0", "python-adapter": "0.1.0"},
        nodes=(
            UnresolvedNode("x"),
            FileNode("b.py", (Definition("function", "z", 9), Definition("class", "A", 2), Definition("method", "A.m", 2))),
            ExternalNode("requests", "third_party"),
            FileNode("a.py"),
        ),
        edges=(
            _edge("file:b.py", "file:a.py", 3),
            _edge("file:a.py", "ext:requests", 5, symbol="b"),
            _edge("file:a.py", "ext:requests", 5, symbol="a"),
            _edge("file:a.py", "unresolved:x", 2, confidence="unresolved", reason="dynamic"),
            _edge("file:a.py", "ext:requests", 2, column=9),
        ),
        files=(CoverageFile("b.py", "python", "analyzed"), CoverageFile("README.md", None, "not_code"), CoverageFile("a.py", "python", "analyzed", ("unreadable", "parse_error"))),
        skipped=(Skipped(".venv", "excluded_dir"), Skipped(".git", "excluded_dir")),
    )


def test_sort_orders():
    d = to_dict(_doc())
    assert [n["id"] for n in d["nodes"]] == ["ext:requests", "file:a.py", "file:b.py", "unresolved:x"]
    keys = [(e["source"], e["line"], e["column"], e["target"], e["symbol"] or "") for e in d["edges"]]
    assert keys == sorted(keys)
    b = next(n for n in d["nodes"] if n["id"] == "file:b.py")
    assert [(x["line"], x["name"]) for x in b["definitions"]] == [(2, "A"), (2, "A.m"), (9, "z")]
    assert [f["path"] for f in d["coverage"]["files"]] == ["README.md", "a.py", "b.py"]
    assert [s["path"] for s in d["coverage"]["skipped"]] == [".git", ".venv"]
    assert d["coverage"]["files"][1]["flags"] == ["parse_error", "unreadable"]


def test_summary():
    s = to_dict(_doc())["coverage"]["summary"]
    assert s == {"analyzed": 2, "detected_only": 0, "not_code": 1, "skipped": 2, "by_language": {"python": 2}}


def test_edge_id():
    e = _edge("file:a.py", "file:b.py", 3, column=4, symbol=None)
    expected = "e:" + hashlib.sha256(b"file:a.py|3|4|file:b.py|").hexdigest()[:16]
    assert edge_id(e) == expected
    assert edge_id(_edge("file:a.py", "file:b.py", 3, column=4, symbol="f")) != expected


def test_reason_only_on_unresolved():
    d = to_dict(_doc())
    for e in d["edges"]:
        assert ("reason" in e) == (e["confidence"] == "unresolved")


def test_dumps_canonical():
    raw = dumps(_doc())
    assert raw.endswith(b"}\n") and not raw.endswith(b"\n\n")
    assert b"\r" not in raw
    assert raw == dumps(_doc())
    parsed = json.loads(raw)
    assert json.dumps(parsed, sort_keys=True, ensure_ascii=False, indent=2).encode() + b"\n" == raw


def test_non_ascii_not_escaped():
    doc = GraphDocument(SNAP, {"python-adapter": "0.1.0"}, (FileNode("ü.py"),), (), (), ())
    assert "ü.py".encode() in dumps(doc)
