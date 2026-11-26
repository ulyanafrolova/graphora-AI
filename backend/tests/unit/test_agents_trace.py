"""The trace: ordered, complete, no repository or model text, identical for identical scripts (specs/012-agents
FR-019, FR-022, SC-006, tasks T027)."""

from agent_world import served
from graphora.agents import ask
from graphora.agents.claims import ClaimItem, ClaimsReply
from scripted_model import call, scripted


def script():
    return scripted(
        call("read_lines", path="api/routes.py"),
        call("dependents", target="auth/service.py"),
        "MODEL TEXT: routes and cli use it",
        call("impact", target="auth/service.py"),
        "MODEL TEXT: done",
        ClaimsReply(
            claims=[
                ClaimItem(statement="MODEL TEXT", cite="c1"),
                ClaimItem(statement="MODEL TEXT", path="web/login.ts", line=1, target="auth/service.py"),
                ClaimItem(statement="MODEL TEXT"),
            ]
        ),
        "MODEL TEXT: nothing new",
        "MODEL TEXT: no tools",
        ClaimsReply(claims=[]),
        "MODEL TEXT summary of api/routes.py",
    )


def run(**kwargs):
    model, _ = script()
    return ask("What breaks if I change auth/service.py?", served(), model=model, **kwargs)


def test_trace_is_ordered_and_complete():
    seen = []
    result = run(on_event=seen.append)
    trace = result.trace
    assert [e.n for e in trace] == list(range(1, len(trace) + 1))
    assert seen == list(trace)
    order = [e.kind for e in trace]
    first = {k: order.index(k) for k in dict.fromkeys(order)}
    assert list(first) == ["role_start", "tool_call", "claim_invalid", "claim", "verdict", "hypothesis", "revision", "summary", "end"]
    assert order[-2:] == ["summary", "end"] and trace[-1].detail == result.answer.end == "answered"
    call0 = trace[1]
    assert (call0.tool, call0.args, call0.citation_ids) == ("read_lines", {"path": "api/routes.py"}, ())


def test_trace_has_no_repository_or_model_text():
    text = run().to_json()
    assert "IGNORE PREVIOUS INSTRUCTIONS" not in text
    trace = "".join(str(e.to_dict()) for e in run().trace)
    assert "MODEL TEXT" not in trace and "class AuthService" not in trace


def test_same_script_same_run():
    assert run().to_json() == run().to_json()
