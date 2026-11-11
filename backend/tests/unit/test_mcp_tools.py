"""MCP tools over a served graph (specs/006-mcp-server contracts/mcp-tools.md)."""

from graphora.graph.queries import index, overview
from graphora.graph.results import dumps, render_text
from graphora.mcp import Served, create_server
from mcp_client import call, canonical, instructions, list_tools, text
from synthetic import SNAP, edge, make_doc


def server(*edges):
    ix = index(make_doc(list(edges) or [edge("a.py", "b.py")]))
    return create_server(Served(ix)), ix


def test_overview_tool():
    srv, ix = server()
    result = call(srv, "graph_overview")
    assert not result.is_error
    assert canonical(result.structured_content) == dumps(overview(ix))
    assert text(result) == render_text(overview(ix))


def test_overview_in_store_mode_names_the_repository():
    ix = index(make_doc([edge("a.py", "b.py")]))
    srv = create_server(Served(ix, repository="github.com/o/r"))
    result = call(srv, "graph_overview")
    assert result.structured_content["repository"] == "github.com/o/r"
    assert text(result).startswith("repository github.com/o/r\n")
    assert f"{SNAP} of github.com/o/r" in instructions(srv)


def test_tools_are_read_only():
    srv, _ = server()
    for tool in list_tools(srv):
        a = tool.annotations
        assert (a.read_only_hint, a.destructive_hint, a.idempotent_hint, a.open_world_hint) == (True, False, True, False)
        assert tool.description


def test_instructions_name_the_snapshot():
    srv, _ = server()
    assert SNAP in instructions(srv)
