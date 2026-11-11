"""SC-003: on a 5,000-file graph the server is ready in < 3 s and each tool call answers in < 1 s
(specs/006-mcp-server)."""

import dataclasses
import time

import anyio
import pytest
from mcp import Client

from graphora.graph import serialize
from graphora.graph.load import loads
from graphora.graph.model import Definition
from graphora.mcp import create_server, from_graph_file
from test_query_performance import _graph

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def graph(tmp_path_factory):
    """The 004 performance graph, with three definitions per file so find_definitions has work to do."""
    doc = loads(_graph())
    nodes = tuple(
        dataclasses.replace(n, definitions=(Definition("class", "Model", 1), Definition("function", f"f{i}", 5), Definition("method", "Model.run", 2)))
        for i, n in enumerate(doc.nodes)
    )
    path = tmp_path_factory.mktemp("perf") / "g.json"
    path.write_bytes(serialize.dumps(dataclasses.replace(doc, nodes=nodes)))
    return path


def test_ready_under_three_seconds(graph):
    start = time.perf_counter()
    create_server(from_graph_file(graph))
    seconds = time.perf_counter() - start
    assert seconds < 3, f"start took {seconds:.2f} s"


def test_each_tool_call_under_one_second(graph):
    server = create_server(from_graph_file(graph))

    async def use():
        timings = {}
        async with Client(server) as client:
            top = await client.call_tool("key_files", {"limit": 1})
            hub = top.structured_content["items"][0]["node"]
            asks = [
                ("graph_overview", {}),
                ("find_definitions", {"name": "run", "limit": 500}),
                ("dependents", {"target": hub, "limit": 500}),
                ("impact", {"target": hub, "limit": 500}),
                ("neighbors", {"target": hub}),
                ("cycles", {"limit": 500}),
                ("key_files", {"limit": 500}),
            ]
            for name, args in asks:
                start = time.perf_counter()
                result = await client.call_tool(name, args)
                timings[name] = (time.perf_counter() - start, result)
        return timings

    for name, (seconds, result) in anyio.run(use).items():
        assert not result.is_error, name
        assert seconds < 1, f"{name} took {seconds:.2f} s"
