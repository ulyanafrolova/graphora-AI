"""The stop signal of the agents: no new model or tool call once it is set (specs/013-ask-sse research R5,
tasks T002)."""

from agent_world import served
from graphora.agents import ask
from graphora.agents.claims import ClaimItem, ClaimsReply
from graphora.agents.review import end_reason
from scripted_model import call, calls, scripted


def test_stop_before_anything():
    model, script = scripted("never used")
    run = ask("q", served(store=False), model=model, stop=lambda: True)
    assert script.calls == [] and run.answer.end == "stopped" and run.answer.facts == ()
    assert run.error is None


def test_stop_after_first_tool_call_keeps_the_running_step_only():
    flag = []
    model, script = scripted(
        calls(("dependents", {"target": "auth/service.py"}), ("cycles", {})),
        "never used",
        ClaimsReply(claims=[ClaimItem(cite="c1")]),
    )

    def on_event(event):
        if event.kind == "tool_call":
            flag.append(True)

    run = ask("q", served(store=False), model=model, on_event=on_event, stop=lambda: bool(flag))
    assert [e.tool for e in run.trace if e.kind == "tool_call"] == ["dependents"]
    assert len(script.calls) == 1 and len(script.replies) == 2
    assert run.answer.end == "stopped"


def test_stop_during_analyst_loop_skips_claims_call():
    state = {"n": 0}

    def stop():
        return state["n"] >= 3

    def count(event):
        if event.kind == "tool_call":
            state["n"] += 1

    model, script = scripted(
        call("dependents", target="auth/service.py"),
        "done",
        call("cycles"),
        call("cycles"),
        ClaimsReply(claims=[ClaimItem(cite="c1")]),
    )
    run = ask("q", served(store=False), model=model, on_event=count, stop=stop)
    assert [k for k, _, _ in script.calls].count("structured") == 0
    assert run.answer.end == "stopped" and run.answer.facts == ()


def test_facts_verified_before_stop_are_kept():
    rounds = []

    def on_event(event):
        if event.kind == "revision":
            rounds.append(event)

    model, script = scripted(
        call("dependents", target="auth/service.py"),
        "found",
        "no tools",
        ClaimsReply(claims=[ClaimItem(cite="c1"), ClaimItem(path="web/login.ts", line=1, target="auth/service.py")]),
        "never used",
    )
    run = ask("q", served(store=False), model=model, on_event=on_event, stop=lambda: bool(rounds))
    assert run.answer.end == "stopped"
    assert [i.cite.split("@")[0] for i in run.answer.facts] == ["api/routes.py:1"]
    assert script.replies == ["never used"]


def test_stopped_comes_first():
    assert end_reason({"failed": "stopped", "tool_calls": 15, "revisions": 2}) == "stopped"
    assert end_reason({"failed": "model_failed"}) == "model_failed"
