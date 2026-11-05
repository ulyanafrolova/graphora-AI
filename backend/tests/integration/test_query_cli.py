"""`graphora query` (specs/004-graph-queries contracts/cli.md)."""

import io
import json
import sys

import pytest

from conftest import analyzed_graph, run_query
from graphora.graph import queries
from graphora.graph.load import loads
from graphora.graph.results import dumps


@pytest.fixture
def graph(tmp_path):
    path = tmp_path / "g.json"
    path.write_bytes(analyzed_graph("py-flat"))
    return str(path)


def test_json_output_is_the_answer(graph):
    code, out, err = run_query(graph, "impact", "pkg/b.py", "--format", "json", "--max-depth", "2")
    assert (code, err) == (0, "")
    expected = queries.impact(queries.index(loads(analyzed_graph("py-flat"))), "pkg/b.py", max_depth=2)
    assert out == dumps(expected)


def test_text_output(graph):
    code, out, err = run_query(graph, "impact", "pkg/b.py")
    text = out.decode("utf-8")
    assert code == 0
    assert "main.py:4 → pkg/a.py:3 → pkg/b.py" in text
    assert "total: 4" in text
    assert "completeness: 4 unresolved imports, 0 files not analyzed, 0 files with errors" in text


def test_dependents_and_dependencies_text(graph):
    assert "pkg/b.py:1 → pkg/a.py" in run_query(graph, "dependents", "pkg/a.py")[1].decode()
    text = run_query(graph, "dependencies", "pkg/c.py")[1].decode()
    assert "pkg/c.py:6 → pkg/sub/__init__.py" in text
    assert "line 2: ...toohigh (unresolved: relative_beyond_top)" in text


def test_cut_line(graph):
    assert "cut at depth 1" in run_query(graph, "impact", "pkg/b.py", "--max-depth", "1")[1].decode()


def test_standard_input(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(analyzed_graph("py-flat"))))
    code, out, err = run_query("-", "dependents", "pkg/a.py", "--format", "json")
    assert code == 0
    assert json.loads(out)["target"] == "file:pkg/a.py"


@pytest.mark.parametrize(
    "args",
    [
        ["what", "pkg/a.py"],
        ["impact"],
        ["cycles", "pkg/a.py"],
        ["dependents", "pkg/a.py", "--limit", "-1"],
        ["impact", "pkg/a.py", "--max-depth", "0"],
        ["dependencies", "pkg/a.py", "--symbol", "x"],
    ],
)
def test_usage_errors(graph, args):
    code, out, err = run_query(graph, *args)
    assert (code, out) == (2, b"")


def test_missing_graph_file(tmp_path):
    code, out, err = run_query(str(tmp_path / "none.json"), "impact", "a.py")
    assert (code, out) == (2, b"")
    assert "cannot read" in err


@pytest.mark.parametrize("content", [b"{}", json.dumps({"schema_version": 1}).encode()])
def test_invalid_graph(tmp_path, content):
    path = tmp_path / "g.json"
    path.write_bytes(content)
    code, out, err = run_query(str(path), "impact", "a.py")
    assert (code, out) == (7, b"")
    assert err.startswith("graphora: error: invalid graph")


def test_not_in_snapshot(graph):
    snapshot = json.loads(analyzed_graph("py-flat"))["snapshot"]
    code, out, err = run_query(graph, "impact", "x.py")
    assert (code, out) == (8, b"")
    assert err == f"graphora: error: x.py is not in snapshot {snapshot}\n"


def test_detected_only(tmp_path):
    path = tmp_path / "g.json"
    path.write_bytes(analyzed_graph("py-dynamic"))
    code, out, err = run_query(str(path), "dependents", "tools/main.go")
    assert (code, out) == (8, b"")
    assert err == "graphora: error: tools/main.go is detected_only (not analyzed)\n"


def test_cycles(graph):
    code, out, err = run_query(graph, "cycles")
    text = out.decode("utf-8")
    assert code == 0
    assert "cycle 1: pkg/a.py, pkg/b.py" in text
    assert "pkg/a.py:3 → pkg/b.py:1 → pkg/a.py" in text
    assert "completeness" not in text


def test_neighbors_and_key_files(graph):
    text = run_query(graph, "neighbors", "pkg/b.py")[1].decode("utf-8")
    assert "imports:\n  pkg/b.py:1 → pkg/a.py" in text
    assert "imported by:\n  pkg/a.py:3 → pkg/b.py" in text
    text = run_query(graph, "key-files")[1].decode("utf-8")
    assert text.splitlines()[1] == "pkg/a.py  transitive 4  direct 4"
    answer = json.loads(run_query(graph, "key-files", "--format", "json")[1])
    assert answer["options"]["limit"] == 10


def test_follow_barrels(tmp_path):
    path = tmp_path / "g.json"
    path.write_bytes(analyzed_graph("ts-barrels"))
    text = run_query(str(path), "dependents", "src/components/Card.tsx", "--follow-barrels")[1].decode("utf-8")
    assert "src/app.ts  src/app.ts:1 → src/components/index.ts:2 → src/components/more.ts:1 → src/components/Card.tsx" in text
