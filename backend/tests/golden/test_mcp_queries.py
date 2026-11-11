"""MCP graph tools answer exactly what `graphora query` answers, on every fixture's queries.json
(specs/006-mcp-server SC-001, FR-010, FR-013)."""

import json

import pytest

from conftest import FIXTURES, analyzed_graph, run_query
from graphora.mcp import create_server, from_graph_file
from mcp_client import calls, canonical, text

CASES = [
    pytest.param(p.parent.name, entry, id=f"{p.parent.name}-{i}-{entry['question']}")
    for p in sorted(FIXTURES.glob("*/queries.json"))
    for i, entry in enumerate(json.loads(p.read_text(encoding="utf-8")))
]


def _flags(options):
    flags = ["--limit", str(options["limit"])]
    if not options.get("include_type_only", True):
        flags.append("--no-type-only")
    if options.get("follow_barrels"):
        flags.append("--follow-barrels")
    if options.get("max_depth") is not None:
        flags += ["--max-depth", str(options["max_depth"])]
    return flags


@pytest.mark.parametrize(("name", "entry"), CASES)
def test_tool_equals_query(name, entry, tmp_path):
    graph = tmp_path / "g.json"
    graph.write_bytes(analyzed_graph(name))
    options = {"limit": 500} | entry["options"]
    target = [] if entry["target"] is None else [entry["target"]]
    args = options | ({} if entry["target"] is None else {"target": entry["target"]})

    first, second = calls(create_server(from_graph_file(graph)), (entry["question"], args), (entry["question"], args))
    question = entry["question"].replace("_", "-")
    code, as_json, err = run_query(str(graph), question, *target, *_flags(options), "--format", "json")
    assert (code, err) == (0, "")
    _, as_text, _ = run_query(str(graph), question, *target, *_flags(options))

    assert not first.is_error, text(first)
    assert canonical(first.structured_content) == as_json
    assert text(first) == as_text.decode("utf-8")
    assert canonical(second.structured_content) == as_json
