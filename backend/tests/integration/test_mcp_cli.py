"""`graphora mcp` start-up checks and `query … overview` (specs/006-mcp-server contracts/cli.md)."""

import io
import sys

import anyio
import pytest
from mcp import Client, StdioServerParameters

from conftest import analyzed_graph, run_query
from graphora.graph.load import loads
from graphora.graph.queries import index, overview
from graphora.graph.results import dumps
from graphora.mcp import create_server, from_graph_file
from mcp_client import call


def run_mcp(*args):
    from graphora.cli import main

    out, err = io.StringIO(), io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = main(["mcp", *args])
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def graph(tmp_path):
    path = tmp_path / "g.json"
    path.write_bytes(analyzed_graph("py-flat"))
    return str(path)


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("--graph", "g.json", "--repository", "r", "--snapshot", "s"),
        ("--graph", "-"),
        ("--graph", "g.json", "--database", "postgresql://x"),
        ("--repository", "r"),
        ("--snapshot", "s"),
    ],
)
def test_usage_errors(args):
    code, out, err = run_mcp(*args)
    assert (code, out) == (2, "")
    assert err.startswith("graphora: error: ")


def test_missing_graph_file(tmp_path):
    code, out, err = run_mcp("--graph", str(tmp_path / "missing.json"))
    assert (code, out) == (2, "")
    assert "cannot read" in err


def test_invalid_graph(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{}")
    code, out, err = run_mcp("--graph", str(path))
    assert (code, out) == (7, "")
    assert "invalid graph" in err


def test_query_overview(graph):
    code, out, err = run_query(graph, "overview", "--format", "json")
    assert (code, err) == (0, "")
    assert out == dumps(overview(index(loads(analyzed_graph("py-flat")))))


@pytest.mark.parametrize("args", [("pkg/a.py",), ("--limit", "3"), ("--no-type-only",)])
def test_query_overview_takes_only_format(graph, args):
    code, out, _ = run_query(graph, "overview", *args)
    assert (code, out) == (2, b"")


def test_real_stdio_server(graph):
    """The command itself as a subprocess: only protocol messages on stdout (research § R11)."""
    command = "from graphora.cli import main; raise SystemExit(main())"
    params = StdioServerParameters(command=sys.executable, args=["-c", command, "mcp", "--graph", graph])

    async def use():
        async with Client(params) as client:
            names = [t.name for t in (await client.list_tools()).tools]
            return names, await client.call_tool("impact", {"target": "pkg/b.py"})

    names, result = anyio.run(use)
    assert "impact" in names
    assert result.structured_content == call(create_server(from_graph_file(graph)), "impact", target="pkg/b.py").structured_content
