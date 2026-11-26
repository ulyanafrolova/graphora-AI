"""The Reviewer: verification, dedupe, hypotheses, revisions and end reasons (specs/012-agents research R4,
tasks T016, T022). Plain code on a served synthetic snapshot."""

from agent_world import SNAP, served
from graphora.agents.claims import claim_key
from graphora.agents.prompts import revision_task
from graphora.agents.review import end_reason, review
from graphora.agents.state import Stated
from graphora.verify import Claim, Step

GOOD = Claim("dependency", "", SNAP, steps=(Step("api/routes.py", 1, "auth/service.py"),))
WRONG_LINE = Claim("dependency", "", SNAP, steps=(Step("cli.py", 1, "auth/service.py"),))
FIXED = Claim("dependency", "", SNAP, steps=(Step("cli.py", 3, "auth/service.py"),))
NO_EDGE = Claim("dependency", "", SNAP, steps=(Step("web/login.ts", 1, "auth/service.py"),))
LIKELY = Claim("dependency", "", SNAP, steps=(Step("db.py", 1, "auth/service.py"),))


def st(claim, rnd=0, revises=None):
    return Stated(claim, claim_key(claim), rnd, revises)


class Events(list):
    def __call__(self, kind, **fields):
        self.append((kind, fields))


def run(state, s=None):
    events = Events()
    update = review({"question": "q", "snapshot": SNAP} | state, s or served(), events)
    return update, events


def test_all_proven_goes_to_answer():
    update, events = run({"claims": [st(GOOD), st(LIKELY), st(GOOD)]})
    assert update["route"] == "answer" and update["hypotheses"] == []
    assert [update["verdicts"][claim_key(c)].status for c in (GOOD, LIKELY)] == ["verified", "heuristic"]
    assert [k for k, _ in events] == ["verdict", "verdict"]


def test_rejected_goes_back_with_reason_and_hint():
    update, events = run({"claims": [st(GOOD), st(WRONG_LINE)]})
    (h,) = update["hypotheses"]
    assert (h.id, h.reason, h.tries, h.open) == ("h1", "edge_not_on_line", 1, True) and "3" in h.hint
    assert update["route"] == "revise" and update["revisions"] == 1 and update["round"] == 1
    assert update["task"] == revision_task([h], 1) and "edge_not_on_line" in update["task"]
    assert [k for k, _ in events] == ["verdict", "verdict", "hypothesis", "revision"]


def test_heuristic_is_not_revised():
    update, _ = run({"claims": [st(LIKELY)]})
    assert update["route"] == "answer"


def test_revision_closes_hypothesis():
    first, _ = run({"claims": [st(WRONG_LINE)]})
    state = {"claims": [st(WRONG_LINE), st(FIXED, 1, "h1")], "round": 1} | {
        k: first[k] for k in ("verdicts", "hypotheses", "revisions")
    }
    update, events = run(state)
    assert update["route"] == "answer" and not update["hypotheses"][0].open
    assert [k for k, _ in events] == ["verdict"]


def test_repeated_rejection_keeps_one_hypothesis_and_stops_after_two_revisions():
    state = {"claims": [st(NO_EDGE)]}
    for rnd in range(3):
        update, _ = run(state)
        state = {
            "claims": state["claims"] + [st(NO_EDGE, rnd + 1)],
            "round": update.get("round", rnd),
            "verdicts": update["verdicts"],
            "hypotheses": update["hypotheses"],
            "revisions": update.get("revisions", state.get("revisions", 0)),
        }
    (h,) = update["hypotheses"]
    assert update["route"] == "answer" and (h.tries, h.reason) == (2, "no_edge")
    assert end_reason({"claims": state["claims"], "hypotheses": [h], "revisions": 2}) == "revisions_spent"


def test_budget_spent_goes_to_answer():
    update, _ = run({"claims": [st(NO_EDGE)], "tool_calls": 15})
    assert update["route"] == "answer" and update["hypotheses"][0].open


def test_end_reason_order():
    h = run({"claims": [st(NO_EDGE)]})[0]["hypotheses"]
    claims = [st(GOOD)]
    assert end_reason({"claims": claims}) == "answered"
    assert end_reason({}) == "no_claims"
    assert end_reason({"claims": claims, "hypotheses": h, "revisions": 2}) == "revisions_spent"
    assert end_reason({"claims": claims, "hypotheses": h, "revisions": 2, "tool_calls": 15}) == "budget_spent"
    assert end_reason({"tool_calls": 15, "failed": "model_budget_spent"}) == "model_budget_spent"
    assert end_reason({"tool_calls": 15, "revisions": 2, "failed": "model_failed"}) == "model_failed"
