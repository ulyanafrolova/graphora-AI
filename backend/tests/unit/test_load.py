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


@pytest.mark.parametrize("version", [1, 2, 4])
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
