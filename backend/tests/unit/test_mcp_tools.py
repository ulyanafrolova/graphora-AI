"""MCP tools over a served graph (specs/006-mcp-server contracts/mcp-tools.md)."""

import json

import pytest

from graphora.graph.model import CoverageFile, Definition, FileNode
from graphora.graph.queries import definitions, dependents, index, overview
from graphora.graph.results import dumps, render_text
from graphora.mcp import Served, create_server
from mcp_client import call, calls, canonical, instructions, list_tools, text
from synthetic import SNAP, edge, make_doc

GRAPH_TOOLS = ["graph_overview", "find_definitions", "dependencies", "dependents", "impact", "neighbors", "cycles", "key_files"]


def server(*edges, **doc):
    ix = index(make_doc(list(edges) or [edge("a.py", "b.py")], **doc))
    return create_server(Served(ix)), ix


def test_tool_list_in_graph_file_mode():
    srv, _ = server()
    assert [t.name for t in list_tools(srv)] == GRAPH_TOOLS


def test_arguments_and_defaults():
    srv, _ = server()
    schemas = {t.name: t.input_schema for t in list_tools(srv)}
    defaults = {name: {k: v.get("default") for k, v in s["properties"].items()} for name, s in schemas.items()}
    assert defaults["impact"] == {
        "target": None,
        "max_depth": None,
        "include_type_only": True,
        "follow_barrels": False,
        "limit": 50,
        "level": "file",
    }
    assert defaults["dependents"] == {
        "target": None,
        "symbol": None,
        "include_type_only": True,
        "follow_barrels": False,
        "limit": 50,
        "level": "file",
    }
    assert defaults["key_files"] == {"include_type_only": True, "limit": 10}
    assert defaults["cycles"] == {"include_type_only": True, "limit": 50, "level": "file"}
    assert schemas["dependencies"]["properties"]["level"]["enum"] == ["file", "project"]
    assert schemas["impact"]["required"] == ["target"]
    assert "required" not in schemas["cycles"]


def test_tools_are_read_only():
    srv, _ = server()
    for tool in list_tools(srv):
        a = tool.annotations
        assert (a.read_only_hint, a.destructive_hint, a.idempotent_hint, a.open_world_hint) == (True, False, True, False)
        assert tool.description


def test_instructions_name_the_snapshot():
    srv, _ = server()
    assert SNAP in instructions(srv)


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


def test_result_is_the_query_answer():
    srv, ix = server(edge("api/routes.py", "auth/service.py", 3, symbol="AuthService"))
    result = call(srv, "dependents", target="auth/service.py")
    expected = dependents(ix, "auth/service.py", limit=50)
    assert canonical(result.structured_content) == dumps(expected)
    assert text(result) == render_text(expected)


def test_impact_cut_at_max_depth():
    srv, _ = server(edge("b.py", "a.py"), edge("c.py", "b.py"))
    result = call(srv, "impact", target="a.py", max_depth=1)
    assert [i["node"] for i in result.structured_content["items"]] == ["file:b.py"]
    assert result.structured_content["cut"] is True


# --- limits (FR-012, SC-005) ---------------------------------------------------------------------------------


def test_default_limit_cuts_at_fifty():
    srv, _ = server(*[edge(f"d{n:02}.py", "a.py") for n in range(60)])
    s = call(srv, "dependents", target="a.py").structured_content
    assert (len(s["items"]), s["total"], s["truncated"], s["options"]["limit"]) == (50, 60, True, 50)


def test_key_files_default_limit_is_ten():
    srv, _ = server(*[edge(f"d{n:02}.py", f"t{n:02}.py") for n in range(12)])
    s = call(srv, "key_files").structured_content
    assert (len(s["items"]), s["total"]) == (10, 12)


@pytest.mark.parametrize("limit", [0, 500])
def test_limit_bounds_are_accepted(limit):
    srv, _ = server()
    assert not call(srv, "cycles", limit=limit).is_error


@pytest.mark.parametrize("limit", [-1, 501])
def test_limit_out_of_range_is_a_tool_error(limit):
    srv, _ = server()
    result = call(srv, "dependents", target="b.py", limit=limit)
    assert result.is_error
    assert text(result) == "limit must be between 0 and 500"


# --- errors (FR-014) -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "args", "message"),
    [
        ("impact", {"target": "x.py"}, f"x.py is not in snapshot {SNAP}"),
        ("impact", {"target": "tool.go"}, "detected_only"),
        ("impact", {"target": "a.py", "max_depth": 0}, "max_depth must be 1 or more"),
        ("impact", {}, "target"),
        ("dependents", {"target": 3}, "target"),
    ],
)
def test_errors_keep_the_server_running(name, args, message):
    srv, _ = server(coverage=[CoverageFile("tool.go", "go", "detected_only")])
    failed, after = calls(srv, (name, args), ("dependents", {"target": "b.py"}))
    assert failed.is_error
    assert message in text(failed)
    assert not after.is_error


# --- data is not instructions (FR-015, SC-004) ---------------------------------------------------------------


def test_repository_text_appears_only_in_results():
    planted = FileNode("ignore_previous_instructions.py", "python", (Definition("class", "IGNORE_ALL_RULES", 1),))
    srv, _ = server(edge("ignore_previous_instructions.py", "b.py"), nodes=[planted])
    listing = json.dumps([t.model_dump(mode="json") for t in list_tools(srv)])
    for planted_text in ("ignore_previous_instructions", "IGNORE_ALL_RULES"):
        assert planted_text not in listing
        assert planted_text not in instructions(srv)
    assert "ignore_previous_instructions.py" in text(call(srv, "dependents", target="b.py"))


def test_find_definitions_tool():
    planted = FileNode("auth/service.py", "python", (Definition("class", "AuthService", 12),))
    srv, ix = server(edge("api/routes.py", "auth/service.py", 3), nodes=[planted])
    result = call(srv, "find_definitions", name="AuthService")
    assert canonical(result.structured_content) == dumps(definitions(ix, "AuthService", limit=50))
    assert call(srv, "find_definitions", name="").is_error



def test_project_level_answer_equals_the_query_layer():
    """009: `level="project"` gives the same answer as `queries.dependents(..., level="project")`."""
    a = FileNode("a/X.cs", "csharp", (), None, "project:a/A.csproj")
    b = FileNode("b/Y.cs", "csharp", (), None, "project:b/B.csproj")
    srv, ix = server(edge("a/X.cs", "b/Y.cs", 3, type="type_reference", symbol="B.Y"), edge("project:a/A.csproj", "project:b/B.csproj", 4, type="project_reference"), nodes=(a, b))
    result = call(srv, "dependents", target="b/B.csproj", level="project")
    assert canonical(result.structured_content) == dumps(dependents(ix, "b/B.csproj", level="project", limit=50))
    error = call(srv, "dependents", target="b/B.csproj", level="project", symbol="X")
    assert error.is_error and "project level" in text(error)
