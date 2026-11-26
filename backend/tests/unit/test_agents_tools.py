"""The 011 tools per role, citation ids and tool messages (specs/012-agents research R3, tasks T005)."""

from agent_world import served
from graphora.agents.limits import MAX_TOOL_MESSAGE_CHARS
from graphora.agents.tools import CitationIds, role_tools, run_tool_call
from graphora.graph.queries import index
from graphora.mcp import Served
from graphora.tools import TOOLS
from synthetic import edge, make_doc


def test_role_tool_lists():
    specs = {s.name: s.description for s in TOOLS}
    explorer = role_tools("explorer", served())
    assert list(explorer.tools) == ["find_definitions", "read_lines", "dependents"]
    assert list(role_tools("explorer", served(store=False)).tools) == ["find_definitions", "dependents"]
    analyst = role_tools("analyst", served())
    assert list(analyst.tools) == ["dependents", "impact", "neighbors", "cycles"]
    for tools in (explorer, analyst):
        assert len(tools.tools) <= 4
        assert all(t.description == specs[n].strip() for n, t in tools.tools.items())


def test_tool_message_has_citation_ids_across_calls():
    tools, ids = role_tools("explorer", served()), CitationIds()
    msg, ev = run_tool_call({"name": "dependents", "args": {"target": "auth/service.py"}, "id": "t1"}, tools, ids, "explorer")
    assert msg.tool_call_id == "t1" and msg.content.startswith(tools.functions["dependents"](target="auth/service.py").text)
    assert "citations:\n[c1] api/routes.py:1@" in msg.content and "[c2] cli.py:3@" in msg.content
    assert ev.citation_ids == ("c1", "c2", "c3") and ev.tool == "dependents" and ev.error is None
    msg2, ev2 = run_tool_call({"name": "find_definitions", "args": {"name": "AuthService"}, "id": "t2"}, tools, ids, "explorer")
    assert ev2.citation_ids == ("c4",) and "[c4] auth/service.py:1@" in msg2.content and "defines AuthService" in msg2.content
    _, again = run_tool_call({"name": "dependents", "args": {"target": "auth/service.py"}, "id": "t3"}, tools, ids, "explorer")
    assert again.citation_ids == ("c1", "c2", "c3")


def test_args_are_sorted():
    tools, ids = role_tools("analyst", served()), CitationIds()
    _, ev = run_tool_call({"name": "impact", "args": {"target": "db.py", "max_depth": 2}, "id": "t"}, tools, ids, "analyst")
    assert list(ev.args) == ["max_depth", "target"]


class Spy:
    def __init__(self, fn):
        self.fn, self.calls = fn, 0

    def __call__(self, **kwargs):
        self.calls += 1
        return self.fn(**kwargs)


def test_bad_calls_do_not_run():
    tools, ids = role_tools("analyst", served()), CitationIds()
    spy = tools.functions["dependents"] = Spy(tools.functions["dependents"])
    for call, expected in [
        ({"name": "read_lines", "args": {"path": "a.py"}}, "unknown tool: read_lines; available: dependents, impact, neighbors, cycles"),
        ({"name": "dependents", "args": {}}, "invalid arguments for dependents: target: Field required"),
        ({"name": "dependents", "args": {"target": "a.py", "offset": "many"}}, "invalid arguments for dependents: offset:"),
        ({"name": "dependents", "args": {"target": "a.py", "colour": 1}}, "unknown arguments for dependents: colour"),
        ({"name": "dependents", "args": None}, "arguments of dependents are not a JSON object"),
    ]:
        msg, ev = run_tool_call(dict(call, id="t"), tools, ids, "analyst")
        assert msg.content.startswith("error: " + expected) and ev.error.startswith(expected)
    assert spy.calls == 0


def test_tool_message_is_bounded():
    long = "deep/" * 60 + "target.py"
    edges = [edge(f"{'very/' * 50}m{n:02}.py", long, 1, symbol="Name") for n in range(20)]
    s = Served(index(make_doc(edges)))
    tools, ids = role_tools("analyst", s), CitationIds()
    msg, ev = run_tool_call({"name": "dependents", "args": {"target": long}, "id": "t"}, tools, ids, "analyst")
    assert len(msg.content) <= MAX_TOOL_MESSAGE_CHARS
    lines = msg.content.split("citations:\n", 1)[1].splitlines()
    shown = [line for line in lines if line.startswith("[c")]
    assert all(len(line) <= 160 and "…" in line for line in shown)
    if len(shown) < len(ev.citation_ids):
        assert lines[-1] == f"(… {len(ev.citation_ids) - len(shown)} more citations)"
    assert set(ev.citation_ids) <= set(ids.claims)
