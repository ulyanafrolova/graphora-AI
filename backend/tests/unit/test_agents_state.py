"""Agent state, answer and trace types (specs/012-agents data-model.md, tasks T003)."""

import typing

from graphora.agents import limits
from graphora.agents.state import END_REASONS, Answer, EndReason, Item, Run, TraceEvent
from graphora.verify import Claim, Step


def test_limits():
    assert limits.MAX_TOOL_CALLS == 15
    assert limits.MAX_REVISIONS == 2
    assert limits.MAX_MODEL_CALLS == 30
    assert limits.MAX_TURN_MODEL_CALLS == 6
    assert limits.MAX_TOOL_MESSAGE_CHARS == 5000


def test_end_reasons():
    assert set(typing.get_args(EndReason)) == set(END_REASONS) == {
        "answered", "revisions_spent", "budget_spent", "model_budget_spent", "model_failed", "no_claims", "stopped"
    }


def test_trace_event_drops_none_and_has_no_time():
    event = TraceEvent(1, "tool_call", "explorer", tool="dependents", args={"target": "a.py"}, citation_ids=("c1",))
    data = event.to_dict()
    assert data == {"n": 1, "kind": "tool_call", "role": "explorer", "tool": "dependents", "args": {"target": "a.py"}, "citation_ids": ["c1"]}
    assert not any("time" in k or "duration" in k for k in data)


def run():
    claim = Claim("dependency", "x", "snap", steps=(Step("a.py", 1, "b.py"),))
    item = Item("`a.py` imports `b.py`", "a.py:1@snap", claim)
    answer = Answer("q", "snap", (item,), (), (), "s", "code", "answered", {"tool_calls": 1, "model_calls": 2, "revisions": 0})
    return Run(answer, (TraceEvent(1, "end", "answer", detail="answered"),))


def test_run_json_is_stable_and_sorted():
    first, second = run().to_json(), run().to_json()
    assert first == second and first.endswith("\n")
    assert first.index('"answer"') < first.index('"trace"')
    assert run().to_dict()["answer"]["facts"][0]["cite"] == "a.py:1@snap"
