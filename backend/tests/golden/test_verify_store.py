"""Text claims on every stored fixture, from the hand-written definitions of expected.json
(specs/011-claim-verifier spec US2, FR-020, SC-001, SC-002)."""

import json

import pytest

from conftest import FIXTURES, analyze_fixture
from graphora.graph import queries
from graphora.mcp import from_store
from graphora.tools import MAX_CHARS, tools_for
from graphora.verify import Claim, verify_served

pytestmark = pytest.mark.db

NAMES = sorted(p.name for p in FIXTURES.iterdir() if (p / "expected.json").is_file())


@pytest.fixture
def served(request, store, database_url):
    name = request.param
    analysis = analyze_fixture(name)
    store.put(name, analysis)
    s = from_store(database_url, name, analysis.doc.snapshot)
    yield name, s
    s.store.close()


def definitions(name):
    nodes = json.loads((FIXTURES / name / "expected.json").read_text(encoding="utf-8"))["nodes"]
    return [(n["id"].removeprefix("file:"), d) for n in nodes for d in n.get("definitions") or ()]


def claim(served, kind, path, line, symbol):
    return Claim(kind, "", served.snapshot, path=path, line=line, symbol=symbol)


@pytest.mark.parametrize("served", NAMES, indirect=True)
def test_every_definition_verifies(served):
    name, s = served
    found = definitions(name)
    claims = [claim(s, "definition", path, d["line"], d["name"]) for path, d in found]
    claims += [claim(s, "mention", path, d["line"], d["name"].rsplit(".", 1)[-1]) for path, d in found]
    for c, v in zip(claims, verify_served(claims, s), strict=True):
        assert v.status == "verified", (c.to_dict(), v.to_dict())


@pytest.mark.parametrize("served", NAMES, indirect=True)
def test_changed_definitions_are_rejected(served):
    name, s = served
    for path, d in definitions(name):
        same = {x["line"] for p, x in definitions(name) if p == path and x["name"] == d["name"]}
        cases = [
            (claim(s, "definition", path, d["line"], "NoSuchName"), {"definition_not_in_graph"}),
            (claim(s, "definition", "missing/x.py", d["line"], d["name"]), {"file_not_in_snapshot"}),
        ]
        if d["line"] + 1 not in same:
            cases.append((claim(s, "definition", path, d["line"] + 1, d["name"]), {"symbol_not_on_line", "line_out_of_range"}))
        for (c, reasons), v in zip(cases, verify_served([c for c, _ in cases], s), strict=True):
            assert v.status == "rejected" and v.reason in reasons, (c.to_dict(), v.to_dict())


def pages(tool, **args):
    """Every page of a tool answer, following `next`."""
    out = [tool(**args)]
    while out[-1].cut:
        key = "start" if "path" in args else "offset"
        out.append(tool(**args, **{key: out[-1].next}))
    return out


def cited(results):
    assert all(r.error is None for r in results), [r.error for r in results if r.error]
    return [c for r in results for c in r.citations]


def statuses(items):
    return ["verified" if i.confidence == "resolved" else "heuristic" for i in items]


@pytest.mark.parametrize("served", NAMES, indirect=True)
def test_every_tool_citation_verifies(served):
    """FR-021, SC-006: tool answers agree with the query layer and every citation verifies."""
    name, s = served
    ix = s.index
    tools = tools_for(s)
    files = sorted(p for p, f in ix.coverage.items() if f.status == "analyzed")
    for path in files:
        for tool, question in (("dependents", queries.dependents), ("impact", queries.impact)):
            claims = cited(pages(tools[tool], target=path))
            expected = statuses(question(ix, path).items)
            assert [v.status for v in verify_served(claims, s)] == expected, (tool, path)
        answer = queries.neighbors(ix, path)
        claims = cited(pages(tools["neighbors"], target=path))
        assert len(claims) == len(answer.incoming) + len(answer.outgoing)
        assert all(v.status != "rejected" for v in verify_served(claims, s)), path
        for r in pages(tools["read_lines"], path=path):
            assert len(r.text) <= MAX_CHARS
            assert r.lines is not None or "empty" in r.text or r.error == f"file has no text content: {path}"
    groups = queries.cycles(ix).groups
    claims = cited(pages(tools["cycles"]))
    assert [v.status for v in verify_served(claims, s)] == statuses(groups)
    for _, d in definitions(name):
        claims = cited(pages(tools["find_definitions"], name=d["name"]))
        assert claims and all(v.status == "verified" for v in verify_served(claims, s)), d
