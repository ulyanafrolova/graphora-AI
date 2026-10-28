import hashlib
import json

from graphora.graph.model import (
    AssetNode,
    CoverageFile,
    Definition,
    Edge,
    Export,
    ExternalNode,
    FileNode,
    GraphDocument,
    Skipped,
    UnresolvedNode,
)
from graphora.graph.serialize import dumps, edge_id, to_dict

SNAP = "content:0123456789abcdef"


def _edge(source, target, line, column=1, symbol=None, confidence="resolved", reason=None, **extra):
    return Edge(source, target, symbol, line, column, SNAP, confidence, reason, "python-adapter@0.2.0", "sha256:0000000000000000", **extra)


def _doc():
    return GraphDocument(
        snapshot=SNAP,
        extractors={"python-resolver": "0.2.0", "python-adapter": "0.2.0"},
        nodes=(
            UnresolvedNode("x", "python"),
            FileNode("b.py", "python", (Definition("function", "z", 9), Definition("class", "A", 2), Definition("method", "A.m", 2))),
            ExternalNode("requests", "python", "third_party"),
            FileNode("a.py", "python"),
        ),
        edges=(
            _edge("file:b.py", "file:a.py", 3),
            _edge("file:a.py", "ext:python:requests", 5, symbol="b"),
            _edge("file:a.py", "ext:python:requests", 5, symbol="a"),
            _edge("file:a.py", "unresolved:python:x", 2, confidence="unresolved", reason="dynamic", form="dynamic"),
            _edge("file:a.py", "ext:python:requests", 2, column=9),
        ),
        files=(CoverageFile("b.py", "python", "analyzed"), CoverageFile("README.md", None, "not_code"), CoverageFile("a.py", "python", "analyzed", ("unreadable", "parse_error"))),
        skipped=(Skipped(".venv", "excluded_dir"), Skipped(".git", "excluded_dir")),
    )


def _ts_doc():
    extractor = "js-adapter@0.1.0"
    h = "sha256:0000000000000000"
    return GraphDocument(
        snapshot=SNAP,
        extractors={"js-adapter": "0.1.0"},
        nodes=(
            FileNode(
                "i.ts",
                "typescript",
                (Definition("class", "C", 3, ("default", "C")), Definition("function", "f", 1, ())),
                (Export("x", "x", 7), Export("b", "a", 5), Export("b", "a", 2)),
            ),
            FileNode("m.ts", "typescript"),
            AssetNode("s.css"),
        ),
        edges=(
            Edge("file:i.ts", "file:m.ts", "a", 4, 1, SNAP, "resolved", None, extractor, h, type="reexports", alias="c"),
            Edge("file:i.ts", "file:m.ts", "a", 4, 1, SNAP, "resolved", None, extractor, h, type="reexports", alias="b"),
            Edge("file:i.ts", "asset:s.css", None, 1, 1, SNAP, "resolved", None, extractor, h),
        ),
        files=(),
        skipped=(),
    )


def _node(d, node_id):
    return next(n for n in d["nodes"] if n["id"] == node_id)


def test_schema_version_2():
    assert to_dict(_doc())["schema_version"] == 2


def test_sort_orders():
    d = to_dict(_doc())
    assert [n["id"] for n in d["nodes"]] == ["ext:python:requests", "file:a.py", "file:b.py", "unresolved:python:x"]
    keys = [(e["source"], e["line"], e["column"], e["target"], e["symbol"] or "", e.get("alias") or "", e["type"]) for e in d["edges"]]
    assert keys == sorted(keys)
    b = _node(d, "file:b.py")
    assert [(x["line"], x["name"]) for x in b["definitions"]] == [(2, "A"), (2, "A.m"), (9, "z")]
    assert [f["path"] for f in d["coverage"]["files"]] == ["README.md", "a.py", "b.py"]
    assert [s["path"] for s in d["coverage"]["skipped"]] == [".git", ".venv"]
    assert d["coverage"]["files"][1]["flags"] == ["parse_error", "unreadable"]


def test_alias_in_sort_order():
    d = to_dict(_ts_doc())
    assert [e.get("alias") for e in d["edges"]] == [None, "b", "c"]


def test_summary():
    s = to_dict(_doc())["coverage"]["summary"]
    assert s == {"analyzed": 2, "detected_only": 0, "not_code": 1, "skipped": 2, "by_language": {"python": 2}}


def test_edge_id():
    e = _edge("file:a.py", "file:b.py", 3, column=4, symbol=None)
    expected = "e:" + hashlib.sha256(b"file:a.py|3|4|file:b.py|||imports").hexdigest()[:16]
    assert edge_id(e) == expected
    assert edge_id(_edge("file:a.py", "file:b.py", 3, column=4, symbol="f")) != expected


def test_edge_id_includes_alias_and_type():
    a, b, _ = _ts_doc().edges
    assert edge_id(a) != edge_id(b)
    expected = "e:" + hashlib.sha256(b"file:i.ts|4|1|file:m.ts|a|c|reexports").hexdigest()[:16]
    assert edge_id(a) == expected


def test_edge_fields():
    d = to_dict(_ts_doc())
    for e in d["edges"]:
        assert e["form"] == "static" and e["type_only"] is False
        assert ("alias" in e) == (e["type"] == "reexports")
    dynamic = next(e for e in to_dict(_doc())["edges"] if e["confidence"] == "unresolved")
    assert dynamic["form"] == "dynamic" and "alias" not in dynamic


def test_reason_only_on_unresolved():
    d = to_dict(_doc())
    for e in d["edges"]:
        assert ("reason" in e) == (e["confidence"] == "unresolved")


def test_python_file_has_no_export_fields():
    b = _node(to_dict(_doc()), "file:b.py")
    assert b["language"] == "python" and "exports" not in b
    assert all("exported_as" not in x for x in b["definitions"])


def test_ts_file_export_fields():
    d = to_dict(_ts_doc())
    i = _node(d, "file:i.ts")
    assert i["language"] == "typescript"
    assert [x["exported_as"] for x in i["definitions"]] == [[], ["C", "default"]]
    assert i["exports"] == [
        {"name": "b", "local": "a", "line": 2},
        {"name": "b", "local": "a", "line": 5},
        {"name": "x", "local": "x", "line": 7},
    ]
    assert _node(d, "file:m.ts")["exports"] == []


def test_ecosystem_ids():
    d = to_dict(_doc())
    assert _node(d, "ext:python:requests") == {
        "id": "ext:python:requests", "kind": "external", "name": "requests", "ecosystem": "python", "category": "third_party",
    }
    assert _node(d, "unresolved:python:x") == {"id": "unresolved:python:x", "kind": "unresolved", "reference": "x", "ecosystem": "python"}
    assert ExternalNode("react", "npm", "third_party").id == "ext:npm:react"
    assert UnresolvedNode("./x", "npm").id == "unresolved:npm:./x"


def test_asset_node():
    assert _node(to_dict(_ts_doc()), "asset:s.css") == {"id": "asset:s.css", "kind": "asset", "path": "s.css"}


def test_dumps_canonical():
    raw = dumps(_doc())
    assert raw.endswith(b"}\n") and not raw.endswith(b"\n\n")
    assert b"\r" not in raw
    assert raw == dumps(_doc())
    parsed = json.loads(raw)
    assert json.dumps(parsed, sort_keys=True, ensure_ascii=False, indent=2).encode() + b"\n" == raw


def test_non_ascii_not_escaped():
    doc = GraphDocument(SNAP, {"python-adapter": "0.2.0"}, (FileNode("ü.py", "python"),), (), (), ())
    assert "ü.py".encode() in dumps(doc)
