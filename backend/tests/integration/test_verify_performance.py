"""SC-005: 100 claims verify in under 1 s, on the largest fixture from the store and on the 5,000-file graph
(specs/011-claim-verifier)."""

import json
import time

import pytest

from conftest import FIXTURES, analyze_fixture
from graphora.graph import queries
from graphora.graph.load import loads
from graphora.mcp import from_store
from graphora.verify import Claim, Step, verify, verify_served
from test_query_performance import _graph

pytestmark = pytest.mark.slow


def largest():
    names = [p.name for p in FIXTURES.iterdir() if (p / "expected.json").is_file()]
    return max(sorted(names), key=lambda n: len(json.loads((FIXTURES / n / "expected.json").read_text())["edges"]))


def mixed(snapshot, edges, definitions, files):
    claims = [Claim("dependency", "", snapshot, steps=(Step(e["source"].split(":", 1)[1], e["line"], e["target"]),)) for e in edges]
    claims += [Claim("definition", "", snapshot, path=p, line=d["line"], symbol=d["name"]) for p, d in definitions]
    claims += [Claim("mention", "", snapshot, path=p, line=d["line"], symbol=d["name"].rsplit(".", 1)[-1]) for p, d in definitions]
    claims += [Claim("query", "", snapshot, question="impact", target=f, member=f) for f in files]
    claims = claims[:100]
    while len(claims) < 100:
        claims += claims[: 100 - len(claims)]
    return claims


@pytest.mark.db
def test_hundred_claims_on_the_largest_fixture(store, database_url):
    name = largest()
    analysis = analyze_fixture(name)
    store.put(name, analysis)
    served = from_store(database_url, name, analysis.doc.snapshot)
    try:
        data = json.loads((FIXTURES / name / "expected.json").read_text())
        definitions = [(n["id"].removeprefix("file:"), d) for n in data["nodes"] for d in n.get("definitions") or ()]
        files = sorted(p for p, f in served.index.coverage.items() if f.status == "analyzed")
        claims = mixed(served.snapshot, data["edges"], definitions, files)
        start = time.perf_counter()
        verdicts = verify_served(claims, served)
        seconds = time.perf_counter() - start
    finally:
        served.store.close()
    assert len(verdicts) == 100
    assert seconds < 1, f"100 claims took {seconds:.2f} s"


def test_hundred_claims_on_a_large_graph():
    ix = queries.index(loads(_graph()))
    edges = [e for e in ix.doc.edges if e.confidence != "unresolved"][:80]
    claims = [Claim("dependency", "", ix.doc.snapshot, steps=(Step(e.source.split(":", 1)[1], e.line, e.target),)) for e in edges]
    target = edges[0].target
    claims += [Claim("query", "", ix.doc.snapshot, question="dependents", target=target, count=1)] * 20
    start = time.perf_counter()
    verdicts = verify(claims, ix)
    seconds = time.perf_counter() - start
    assert all(v.status != "rejected" or v.reason == "count_mismatch" for v in verdicts)
    assert seconds < 1, f"100 claims took {seconds:.2f} s"
