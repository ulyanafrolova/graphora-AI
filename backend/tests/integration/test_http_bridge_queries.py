"""HTTP edges in graph answers, verifier verdicts and agent answers (specs/015-http-bridge US1, FR-012, FR-013,
SC-003, SC-005, SC-006; tasks T014)."""

import sys
from pathlib import Path

from conftest import FIXTURES, run_analyze
from graphora.agents import ask
from graphora.agents.claims import ClaimItem, ClaimsReply
from graphora.graph import queries
from graphora.graph.load import loads
from graphora.graph.results import render_text
from graphora.mcp import Served
from graphora.verify import Claim, Step, verify

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from scripted_model import call, scripted  # noqa: E402

REPO = FIXTURES / "http-bridge" / "repo"


def graph():
    code, out, err = run_analyze(REPO)
    assert code == 0, err
    return out


def index():
    return queries.index(loads(graph()))


def test_dependents_and_impact_show_frontend_as_likely():
    ix = index()
    answer = queries.dependents(ix, "backend/app/items.py")
    by_node = {i.node: i for i in answer.items}
    assert {"file:frontend/src/items.ts", "file:frontend/src/misc.ts"} <= set(by_node)
    assert all(by_node[n].confidence == "heuristic" for n in ("file:frontend/src/items.ts", "file:frontend/src/misc.ts"))
    lines = render_text(answer).splitlines()
    assert "frontend/src/items.ts  frontend/src/items.ts:4 → backend/app/items.py (likely)" in lines
    impact = queries.impact(ix, "backend/app/items.py")
    assert {i.node: i.confidence for i in impact.items}["file:frontend/src/items.ts"] == "heuristic"


def test_symbol_filter_keeps_one_method():
    answer = queries.dependents(index(), "backend/app/items.py", symbol="GET /api/items")
    lines = sorted(e.line for i in answer.items for link in i.chain for e in link.edges)
    assert lines == [4, 16]


def test_claim_on_the_call_line_is_only_likely():
    ix = index()
    claim = Claim("dependency", "the frontend loads items", ix.doc.snapshot,
                  steps=(Step("frontend/src/items.ts", 4, "backend/app/items.py"),))
    (verdict,) = verify([claim], ix)
    assert verdict.status == "heuristic" and not verdict.fact


def test_agents_report_the_http_link_as_likely():
    served = Served(index())
    model, _ = scripted(
        call("dependents", target="backend/app/items.py"),
        "found",
        "no tools",
        ClaimsReply(claims=[ClaimItem(statement="the frontend will break", path="frontend/src/items.ts", line=4,
                                      target="backend/app/items.py")]),
        "frontend/src/items.ts likely calls backend/app/items.py.",
    )
    answer = ask("Will the frontend break if I change the items API?", served, model=model).answer
    assert [i.cite.split("@")[0] for i in answer.likely] == ["frontend/src/items.ts:4"]
    assert answer.facts == () and answer.hypotheses == ()


def test_two_analyses_are_byte_identical():
    assert graph() == graph()
