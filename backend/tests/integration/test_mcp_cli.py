"""`graphora mcp` start-up checks and `query … overview` (specs/006-mcp-server contracts/cli.md)."""

import io
import sys

import pytest

from conftest import analyzed_graph, run_query
from graphora.graph.load import loads
from graphora.graph.queries import index, overview
from graphora.graph.results import dumps


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
