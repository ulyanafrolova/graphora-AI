"""Loading the served snapshot (specs/006-mcp-server research § R2)."""

import json

import pytest

from conftest import analyzed_graph
from graphora.graph.load import InvalidGraph
from graphora.mcp import from_graph_file


def test_graph_file(tmp_path):
    path = tmp_path / "g.json"
    path.write_bytes(analyzed_graph("py-flat"))
    served = from_graph_file(path)
    assert served.snapshot == json.loads(path.read_bytes())["snapshot"]
    assert (served.repository, served.store) == (None, None)


def test_missing_file(tmp_path):
    with pytest.raises(OSError):
        from_graph_file(tmp_path / "missing.json")


def test_invalid_graph(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{}")
    with pytest.raises(InvalidGraph):
        from_graph_file(path)
