"""The MCP hotspots tool and the history line of graph_overview (specs/014-hotspots contracts/interfaces.md)."""

import dataclasses

from graphora.graph.model import FileHistory, History, not_available
from graphora.graph.queries import hotspots, index, overview
from graphora.graph.results import dumps, render_text
from graphora.mcp import Served, create_server
from mcp_client import call, canonical, list_tools, text
from synthetic import edge, make_doc

HISTORY = History(
    "available", None, "f" * 40, "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "2025-02-01T00:00:00Z", 9, 0, 0,
    False, (FileHistory("a.py", 4, 2), FileHistory("b.py", 2, 1)),
)


def server(history=HISTORY):
    doc = dataclasses.replace(make_doc([edge("b.py", "a.py"), edge("c.py", "b.py")]), history=history)
    ix = index(doc)
    return create_server(Served(ix)), ix


def test_listed_read_only_after_key_files():
    srv, _ = server()
    tools = {t.name: t for t in list_tools(srv)}
    names = list(tools)
    assert names.index("hotspots") == names.index("key_files") + 1
    tool = tools["hotspots"]
    assert tool.annotations.read_only_hint is True
    assert tool.description.startswith("Files that change often and that many files depend on")
    props = tool.input_schema["properties"]
    assert {k: v.get("default") for k, v in props.items()} == {"include_type_only": True, "limit": 10}


def test_answer_equals_the_query():
    srv, ix = server()
    result = call(srv, "hotspots", limit=1)
    assert canonical(result.structured_content) == dumps(hotspots(ix, limit=1))
    assert text(result) == render_text(hotspots(ix, limit=1))
    assert result.structured_content["items"][0]["node"] == "file:a.py"


def test_limit_checked():
    srv, _ = server()
    result = call(srv, "hotspots", limit=501)
    assert result.is_error


def test_overview_history():
    srv, ix = server(not_available("zip"))
    result = call(srv, "graph_overview")
    assert result.structured_content["history"] == {"status": "not_available", "reason": "zip"}
    assert "history: not available (zip)" in text(result).splitlines()
    assert overview(ix).to_dict()["history"]["reason"] == "zip"
