"""Dependency, chain and query result claims on synthetic graphs (specs/011-claim-verifier spec US1, research § R5, R7)."""

import pytest

from graphora.graph.model import CoverageFile, Definition, FileNode, ProjectNode, SolutionNode
from graphora.graph.queries import index
from graphora.verify import Claim, Step, dumps, verify
from synthetic import SNAP, edge, make_doc


def dep(path, line, target, name=None, snapshot=SNAP):
    return Claim("dependency", "", snapshot, steps=(Step(path, line, target, name),))


def chain(*steps):
    return Claim("chain", "", SNAP, steps=tuple(Step(*s) for s in steps))


def query(question, target=None, **fields):
    return Claim("query", "", SNAP, question=question, target=target, **fields)


def one(doc, claim):
    (verdict,) = verify([claim], index(doc))
    return verdict


def routes():
    return make_doc([edge("api/routes.py", "auth/service.py", 3, symbol="AuthService")])


# --- dependency ---------------------------------------------------------------------------------------------


def test_resolved_edge_on_the_cited_line():
    v = one(routes(), dep("api/routes.py", 3, "auth/service.py"))
    assert (v.status, v.fact, v.reason) == ("verified", True, None)
    (proof,) = v.proof
    assert (proof.source, proof.target, proof.line) == ("file:api/routes.py", "file:auth/service.py", 3)
    assert [c.name for c in v.checks] == ["snapshot", "source", "target", "edge", "line"]


def test_edge_on_another_line():
    v = one(routes(), dep("api/routes.py", 5, "auth/service.py"))
    assert (v.status, v.reason, v.hint) == ("rejected", "edge_not_on_line", "edge on line 3")
    doc = make_doc([edge("a.py", "b.py", 3), edge("a.py", "b.py", 9, symbol="x")])
    assert one(doc, dep("a.py", 5, "b.py")).hint == "edges on lines 3, 9"


def test_no_edge():
    doc = make_doc([edge("api/routes.py", "auth/service.py", 3)], files=["frontend/login.ts"])
    v = one(doc, dep("frontend/login.ts", 1, "auth/service.py"))
    assert (v.status, v.reason, v.fact) == ("rejected", "no_edge", False)


def test_reviewer_example_frontend_does_not_import_python():
    """SC-007: "the frontend will break" with no TS → Python edge."""
    doc = make_doc([edge("frontend/app.ts", "frontend/login.ts", 2)], files=["auth/service.py"])
    assert one(doc, dep("frontend/login.ts", 1, "auth/service.py")).reason == "no_edge"


def test_heuristic_edge_only():
    doc = make_doc([edge("App/P.cs", "App/M.cs", 4, confidence="heuristic")])
    v = one(doc, dep("App/P.cs", 4, "App/M.cs"))
    assert (v.status, v.fact) == ("heuristic", False)


def test_resolved_and_heuristic_on_the_line():
    doc = make_doc([edge("a.cs", "b.cs", 4, confidence="heuristic"), edge("a.cs", "b.cs", 4, column=9)])
    assert one(doc, dep("a.cs", 4, "b.cs")).status == "verified"


def test_unresolved_import_proves_nothing():
    doc = make_doc([edge("a.py", "unresolved:python:foo", 2)], files=["foo.py"])
    assert one(doc, dep("a.py", 2, "foo.py")).reason == "import_unresolved"
    assert one(doc, dep("a.py", 2, "unresolved:python:foo")).reason == "import_unresolved"
    assert one(doc, dep("a.py", 7, "foo.py")).reason == "no_edge"


def test_imported_name():
    assert one(routes(), dep("api/routes.py", 3, "auth/service.py", "AuthService")).status == "verified"
    v = one(routes(), dep("api/routes.py", 3, "auth/service.py", "hash_password"))
    assert (v.reason, v.hint) == ("name_not_imported", "imported on line 3: AuthService")


def test_imported_name_follows_the_query_rule():
    alias = make_doc([edge("index.ts", "log.ts", 1, symbol="Log", alias="Logger", type="reexports")])
    assert one(alias, dep("index.ts", 1, "log.ts", "Logger")).status == "verified"
    types = make_doc([edge("App/P.cs", "App/M.cs", 9, type="type_reference", symbol="App.Services.Mailer")])
    assert one(types, dep("App/P.cs", 9, "App/M.cs", "Mailer")).status == "verified"
    assert one(types, dep("App/P.cs", 9, "App/M.cs", "ailer")).reason == "name_not_imported"


def test_source_not_analyzed_or_missing():
    doc = make_doc([edge("a.py", "b.py")], coverage=[CoverageFile("tool.rb", "ruby", "detected_only")])
    assert one(doc, dep("tool.rb", 1, "b.py")).reason == "file_not_analyzed"
    assert one(doc, dep("missing/x.py", 1, "b.py")).reason == "file_not_in_snapshot"


def test_unknown_target():
    v = one(routes(), dep("api/routes.py", 3, "nowhere.py"))
    assert v.reason == "target_not_found"
    assert "not in snapshot" in v.hint


def test_snapshot_mismatch():
    v = one(routes(), dep("api/routes.py", 3, "auth/service.py", snapshot="other"))
    assert (v.reason, [c.name for c in v.checks]) == ("snapshot_mismatch", ["snapshot"])


def test_invalid_claim_does_not_stop_the_others():
    bad = Claim("dependency", "", SNAP, steps=(Step("api/routes.py", 0, "auth/service.py"),))
    verdicts = verify([bad, dep("api/routes.py", 3, "auth/service.py")], index(routes()))
    assert [v.reason for v in verdicts] == ["invalid_claim", None]


def test_project_and_solution_sources():
    doc = make_doc(
        [
            edge("project:App/App.csproj", "project:Lib/Lib.csproj", 7, type="project_reference"),
            edge("solution:All.sln", "project:App/App.csproj", 5, type="solution_member"),
        ],
        nodes=[ProjectNode("App/App.csproj"), ProjectNode("Lib/Lib.csproj"), SolutionNode("All.sln")],
    )
    assert one(doc, dep("App/App.csproj", 7, "Lib/Lib.csproj")).status == "verified"
    assert one(doc, dep("All.sln", 5, "App/App.csproj")).status == "verified"


def test_type_only_edge_is_said_so():
    doc = make_doc([edge("a.ts", "b.ts", 1, type_only=True)])
    v = one(doc, dep("a.ts", 1, "b.ts"))
    assert v.status == "verified"
    assert "type-only" in v.checks[-1].detail


# --- chain --------------------------------------------------------------------------------------------------


def three():
    return make_doc([edge("c.py", "b.py", 1), edge("b.py", "a.py", 2), edge("a.py", "z.py", 4, confidence="heuristic")])


def test_chain_all_resolved():
    v = one(three(), chain(("c.py", 1, "b.py"), ("b.py", 2, "a.py")))
    assert (v.status, len(v.proof)) == ("verified", 2)


def test_chain_takes_the_weakest_step():
    assert one(three(), chain(("c.py", 1, "b.py"), ("b.py", 2, "a.py"), ("a.py", 4, "z.py"))).status == "heuristic"


def test_chain_names_the_failing_step():
    v = one(three(), chain(("c.py", 1, "b.py"), ("b.py", 9, "a.py"), ("a.py", 4, "z.py")))
    assert (v.status, v.reason, v.step) == ("rejected", "edge_not_on_line", 2)


def test_unconnected_chain():
    v = one(three(), chain(("c.py", 1, "b.py"), ("a.py", 4, "z.py")))
    assert (v.reason, v.step) == ("invalid_claim", 2)


def test_closed_chain_is_a_cycle():
    doc = make_doc([edge("x.py", "y.py", 1), edge("y.py", "x.py", 1)])
    assert one(doc, chain(("x.py", 1, "y.py"), ("y.py", 1, "x.py"))).status == "verified"


def test_barrel_link_as_a_chain():
    card = FileNode("Card.tsx", "typescript", (Definition("function", "Card", 1, ("Card",)),), ())
    doc = make_doc(
        [edge("app.ts", "index.ts", 1, symbol="Card"), edge("index.ts", "Card.tsx", 3, symbol="Card", type="reexports")],
        nodes=[card],
    )
    assert one(doc, chain(("app.ts", 1, "index.ts", "Card"), ("index.ts", 3, "Card.tsx", "Card"))).status == "verified"
    assert one(doc, dep("app.ts", 1, "Card.tsx")).reason == "no_edge"


# --- query results ------------------------------------------------------------------------------------------


def star():
    """core.py has 3 direct dependents (one heuristic) and util.py one more through api.py."""
    return make_doc(
        [
            edge("api.py", "core.py", 1),
            edge("cli.py", "core.py", 2),
            edge("web.py", "core.py", 3, confidence="heuristic"),
            edge("util.py", "api.py", 1),
            edge("x.py", "y.py", 1),
            edge("y.py", "x.py", 1),
        ]
    )


def test_count():
    v = one(star(), query("dependents", "core.py", count=3))
    assert (v.status, v.proof) == ("heuristic", ())
    v = one(star(), query("dependents", "core.py", count=4))
    assert (v.reason, v.hint) == ("count_mismatch", "actual 3")
    assert one(star(), query("dependents", "api.py", count=1)).status == "verified"


def test_count_is_the_full_total():
    edges = [edge(f"m{n:02}.py", "core.py", 1) for n in range(60)]
    assert one(make_doc(edges), query("dependents", "core.py", count=60)).status == "verified"


def test_impact_member_and_distance():
    v = one(star(), query("impact", "core.py", member="util.py", distance=2))
    assert v.status == "verified"
    assert [(e.source, e.line) for e in v.proof] == [("file:api.py", 1), ("file:util.py", 1)]
    v = one(star(), query("impact", "core.py", member="util.py", distance=1))
    assert (v.reason, v.hint) == ("not_in_result", "at distance 2")
    assert one(star(), query("impact", "core.py", member="x.py")).reason == "not_in_result"
    assert one(star(), query("impact", "core.py", options={"max_depth": 1}, member="util.py")).reason == "not_in_result"


def test_member_takes_the_item_confidence():
    assert one(star(), query("dependents", "core.py", member="web.py")).status == "heuristic"
    assert one(star(), query("dependents", "core.py", member="cli.py")).status == "verified"


def test_neighbors_member_in_either_list():
    assert one(star(), query("neighbors", "api.py", member="core.py")).status == "verified"
    assert one(star(), query("neighbors", "api.py", member="util.py")).status == "verified"
    assert one(star(), query("neighbors", "api.py", count=2)).status == "verified"


def test_cycles_count_and_member():
    assert one(star(), query("cycles", count=1)).status == "verified"
    assert one(star(), query("cycles", count=2)).reason == "count_mismatch"
    assert one(star(), query("cycles", member="y.py")).status == "verified"
    assert one(star(), query("cycles", member="core.py")).reason == "not_in_result"


def test_key_files_rank():
    assert one(star(), query("key_files", member="core.py", rank=1)).status == "heuristic"
    v = one(star(), query("key_files", member="api.py", rank=1))
    assert (v.reason, v.hint) == ("rank_mismatch", "rank 2")
    v = one(star(), query("key_files", member="util.py", rank=3))
    assert (v.reason, v.hint) == ("rank_mismatch", "not ranked")
    assert one(star(), query("key_files", member="api.py")).status == "verified"


def test_query_errors():
    assert one(star(), query("dependents", "nowhere.py", count=1)).reason == "target_not_found"
    assert one(star(), query("impact", "core.py", options={"max_depth": 0}, count=1)).reason == "invalid_claim"


def test_verdicts_in_claim_order_and_stable():
    claims = [query("cycles", count=1), dep("api.py", 9, "core.py"), dep("cli.py", 2, "core.py")]
    ix = index(star())
    first = verify(claims, ix)
    assert [v.status for v in first] == ["verified", "rejected", "verified"]
    assert dumps(first) == dumps(verify(claims, ix))


@pytest.mark.parametrize("kind", ["definition", "mention"])
def test_text_claims_without_text(kind):
    claim = Claim(kind, "", SNAP, path="api/routes.py", line=3, symbol="AuthService")
    assert one(routes(), claim).reason == "text_unavailable"
