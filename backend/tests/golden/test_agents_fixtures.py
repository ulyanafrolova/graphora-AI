"""Agent scenarios on fixture snapshots with a scripted model (specs/012-agents US1, US2, SC-001, SC-002,
SC-004, SC-005, tasks T017, T023). Each runs on the analyzed graph file and, marked `db`, on the stored analysis.
Assertions are on structure, never on wording."""

import json
import sys
from pathlib import Path

import pytest

from conftest import FIXTURES, analyze_fixture, analyzed_graph
from graphora.agents import ask
from graphora.agents.claims import ClaimItem, ClaimsReply
from graphora.graph.load import loads
from graphora.graph.queries import index
from graphora.mcp import Served, from_store
from graphora.verify import verify_served

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from scripted_model import call, scripted  # noqa: E402

MODES = ["graph", pytest.param("store", marks=pytest.mark.db)]


def serve(request, name):
    if request.param == "graph":
        return Served(index(loads(analyzed_graph(name))))
    store, url = request.getfixturevalue("store"), request.getfixturevalue("database_url")
    analysis = analyze_fixture(name)
    store.put(name, analysis)
    served = from_store(url, name, analysis.doc.snapshot)
    request.addfinalizer(served.store.close)
    return served


def direct_dependents(name, target):
    edges = json.loads((FIXTURES / name / "expected.json").read_text(encoding="utf-8"))["edges"]
    return sorted({e["source"].removeprefix("file:") for e in edges if e["target"] == f"file:{target}" and e["confidence"] == "resolved"})


def facts_reverify(run, served):
    claims = [i.claim for i in run.answer.facts]
    assert all(v.status == "verified" for v in verify_served(claims, served))
    likely = [i.claim for i in run.answer.likely]
    assert all(v.status == "heuristic" for v in verify_served(likely, served))


def explorer_messages(script, round_no):
    """The human message of the explorer's first call in each round."""
    firsts = [m for kind, m, tools in script.calls if kind == "chat" and "find_definitions" in tools and len(m) == 2]
    return [m[1].content for m in firsts][round_no]


@pytest.fixture(params=MODES)
def py_cycles(request):
    return serve(request, "py-cycles")


@pytest.fixture(params=MODES)
def mixed(request):
    return serve(request, "mixed-fullstack")


@pytest.fixture(params=MODES)
def py_flat(request):
    return serve(request, "py-flat")


def what_breaks(summary):
    return scripted(
        call("dependents", target="loop/a.py"),
        "loop/a.py is imported by the files in c1 and c2.",
        call("impact", target="loop/a.py"),
        "done",
        ClaimsReply(
            claims=[
                ClaimItem(statement="c imports a", cite="c1"),
                ClaimItem(statement="user imports a", cite="c2"),
                ClaimItem(statement="two dependents", question="dependents", target="loop/a.py", count=2),
            ]
        ),
        summary,
    )


def test_what_breaks_facts_are_all_proven(py_cycles):
    model, script = what_breaks("Changing loop/a.py breaks loop/c.py and user.py (user.py:1).")
    run = ask("What breaks if I change loop/a.py?", py_cycles, model=model)
    answer = run.answer
    sources = sorted({i.claim.steps[0].path for i in answer.facts if i.claim.steps})
    assert sources == direct_dependents("py-cycles", "loop/a.py") == ["loop/c.py", "user.py"]
    assert any(i.cite == f"dependents(loop/a.py)@{py_cycles.snapshot}" for i in answer.facts)
    assert all(i.cite for i in answer.facts) and answer.likely == () and answer.hypotheses == ()
    assert answer.end == "answered" and answer.summary_source == "model"
    assert answer.counts["tool_calls"] == 2 and not script.replies
    facts_reverify(run, py_cycles)


def test_summary_naming_an_unproven_file_is_replaced(py_cycles):
    model, _ = what_breaks("It also breaks pair/x.py.")
    answer = ask("What breaks if I change loop/a.py?", py_cycles, model=model).answer
    assert answer.summary_source == "code" and "pair/x.py" not in answer.summary


def test_missing_file_gives_no_facts(py_cycles):
    model, _ = scripted(call("dependents", target="nope.py"), "not found", "nothing to do", ClaimsReply(claims=[]))
    answer = ask("What breaks if I change nope.py?", py_cycles, model=model).answer
    assert answer.facts == () and answer.end == "no_claims"
    assert answer.summary == "`nope.py` was not found in the snapshot; nothing could be verified."


def test_frontend_claim_ends_as_hypothesis(mixed):
    frontend = ClaimItem(statement="the frontend will break", path="frontend/src/api.ts", line=1, target="backend/app/api.py")
    revised = frontend.model_copy(update={"revises": "h1"})
    model, script = scripted(
        call("dependents", target="backend/app/api.py"),
        "nothing imports it",
        "no tools",
        ClaimsReply(claims=[frontend]),
        "still nothing",
        "no tools",
        ClaimsReply(claims=[revised]),
        "still nothing",
        "no tools",
        ClaimsReply(claims=[revised]),
    )
    answer = ask("Will the frontend break if I change backend/app/api.py?", mixed, model=model).answer
    (h,) = answer.hypotheses
    assert (h.claim.steps[0].path, h.reason) == ("frontend/src/api.ts", "no_edge")
    assert answer.facts == () and answer.likely == ()
    assert answer.end == "revisions_spent" and answer.counts["revisions"] == 2
    for round_no in (1, 2):
        assert f"Revision {round_no} of 2" in explorer_messages(script, round_no)
        assert "h1: dependency frontend/src/api.ts:1 → backend/app/api.py — no_edge" in explorer_messages(script, round_no)


def test_wrong_line_is_corrected_from_the_hint(py_flat):
    wrong = ClaimItem(statement="main imports a", path="main.py", line=7, target="pkg/a.py")
    fixed = ClaimItem(statement="main imports a", path="main.py", line=4, target="pkg/a.py", revises="h1")
    model, script = scripted(
        "main.py imports pkg/a.py",
        "no tools",
        ClaimsReply(claims=[wrong]),
        "the hint says line 4",
        "no tools",
        ClaimsReply(claims=[fixed]),
        "main.py imports pkg/a.py at main.py:4.",
    )
    run = ask("Does main.py use pkg/a.py?", py_flat, model=model)
    assert "edge_not_on_line (edge not on the cited line) (hint:" in explorer_messages(script, 1)
    assert [i.cite for i in run.answer.facts] == [f"main.py:4@{py_flat.snapshot}"]
    assert run.answer.hypotheses == () and run.answer.end == "answered" and run.answer.summary_source == "model"
    facts_reverify(run, py_flat)
