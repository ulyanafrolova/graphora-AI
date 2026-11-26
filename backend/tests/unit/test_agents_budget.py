"""Limits under misbehaving models (specs/012-agents US3, FR-006–FR-008, SC-003, tasks T026). Synthetic graph,
scripted model."""

import functools

import httpx
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage

import graphora.agents.graph as graph_module
import graphora.agents.tools as tools_module
from agent_world import served
from graphora.agents import ask
from graphora.agents.answer import UNRELATED
from graphora.agents.claims import ClaimItem, ClaimsReply
from graphora.agents.tools import BUDGET_SPENT
from scripted_model import call, calls, scripted

DEP = ("dependents", {"target": "auth/service.py"})


def kinds(run, kind):
    return [e for e in run.trace if e.kind == kind]


def test_tool_budget_stops_at_15_and_claims_still_count():
    model, script = scripted(
        calls(*[DEP] * 4), calls(*[DEP] * 4), calls(*[DEP] * 4), calls(*[DEP] * 4),
        ClaimsReply(claims=[ClaimItem(statement="routes", cite="c1")]),
        "summary of api/routes.py",
    )
    run = ask("what breaks?", served(store=False), model=model)
    tool_events = kinds(run, "tool_call")
    assert len(tool_events) == 16 and run.answer.counts["tool_calls"] == 15
    assert [e.error for e in tool_events][-1] == BUDGET_SPENT and all(e.error is None for e in tool_events[:15])
    assert [k for k, _, _ in script.calls].count("structured") == 1 and not script.replies
    assert [i.cite.split("@")[0] for i in run.answer.facts] == ["api/routes.py:1"]
    assert run.answer.end == "budget_spent"


def test_bad_calls_count_and_do_not_run(monkeypatch):
    ran = []
    real = tools_module.tools_for

    def spy(name, fn):
        @functools.wraps(fn)
        def wrapper(**kwargs):
            ran.append(name)
            return fn(**kwargs)

        return wrapper

    def spying(s):
        return {n: spy(n, f) for n, f in real(s).items()}

    monkeypatch.setattr(tools_module, "tools_for", spying)
    broken = AIMessage(content="", invalid_tool_calls=[{"name": "dependents", "args": "{bad", "id": "tb", "error": None, "type": "invalid_tool_call"}])
    model, _ = scripted(
        calls(("nope", {}), ("dependents", {}), ("dependents", {"target": "x.py", "colour": 1})),
        broken,
        "giving up",
        "nothing",
        ClaimsReply(claims=[]),
    )
    run = ask("q", served(store=False), model=model)
    errors = [e.error for e in kinds(run, "tool_call")]
    assert len(errors) == 4 and all(errors) and ran == []
    assert errors[0].startswith("unknown tool: nope") and "not a JSON object" in errors[3]
    assert run.answer.counts["tool_calls"] == 4


def test_text_only_replies():
    model, _ = scripted("I like poems.", "Roses are red.", ClaimsReply(claims=[]))
    answer = ask("write me a poem", served(store=False), model=model).answer
    assert answer.facts == answer.likely == answer.hypotheses == ()
    assert answer.end == "no_claims" and answer.summary == UNRELATED and "nothing could be verified" in answer.summary


def test_turn_caps_and_claims_call_always_left():
    model, script = scripted(*[call("cycles")] * 6, *[call("cycles")] * 5, ClaimsReply(claims=[]))
    run = ask("q", served(store=False), model=model)
    tools_per_call = [t for kind, _, t in script.calls]
    assert tools_per_call.count(("find_definitions", "dependents")) == 6
    assert tools_per_call.count(("dependents", "impact", "neighbors", "cycles")) == 5
    assert [k for k, _, _ in script.calls][-1] == "structured" and not script.replies
    assert run.answer.counts["model_calls"] == 12 and run.answer.counts["tool_calls"] == 11


def test_run_model_budget(monkeypatch):
    monkeypatch.setattr(graph_module, "MAX_MODEL_CALLS", 3)
    model, script = scripted(call("cycles"), call("cycles"), call("cycles"))
    answer = ask("q", served(store=False), model=model).answer
    assert answer.end == "model_budget_spent" and answer.counts["model_calls"] == 3 and not script.replies


def test_model_error_mid_run_keeps_facts():
    model, _ = scripted(
        call("dependents", target="auth/service.py"),
        "found",
        "no tools",
        ClaimsReply(claims=[ClaimItem(cite="c1"), ClaimItem(path="web/login.ts", line=1, target="auth/service.py")]),
        httpx.ConnectError("connection refused"),
    )
    answer = ask("q", served(store=False), model=model).answer
    assert answer.end == "model_failed"
    assert [i.cite.split("@")[0] for i in answer.facts] == ["api/routes.py:1"] and len(answer.hypotheses) == 1


def test_unreadable_claims_reply():
    model, _ = scripted("x", "y", OutputParserException("not json"))
    run = ask("q", served(store=False), model=model)
    assert [e.detail for e in kinds(run, "claim_invalid")] == ["the claims reply could not be read"]
    assert run.answer.counts["model_calls"] == 3 and run.answer.end == "no_claims"


def test_failing_callback_ends_the_run():
    def boom(event):
        if event.kind == "tool_call":
            raise RuntimeError("client went away")

    model, script = scripted(call("cycles"), call("cycles"), "x", "y", ClaimsReply(claims=[]))
    answer = ask("q", served(store=False), model=model, on_event=boom).answer
    assert answer.end == "model_failed" and answer.counts["tool_calls"] == 1


def test_graph_file_without_text():
    model, script = scripted(
        call("find_definitions", name="AuthService"),
        call("dependents", target="auth/service.py"),
        "found",
        "no tools",
        ClaimsReply(claims=[ClaimItem(cite="c1"), ClaimItem(cite="c2")]),
        "nothing more",
        "no tools",
        ClaimsReply(claims=[]),
        "api/routes.py imports auth/service.py.",
    )
    answer = ask("q", served(store=False), model=model).answer
    assert all("read_lines" not in t for _, _, t in script.calls)
    (h,) = answer.hypotheses
    assert (h.claim.kind, h.reason) == ("definition", "text_unavailable")
    assert [i.claim.kind for i in answer.facts] == ["dependency"]
