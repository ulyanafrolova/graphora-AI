"""Text claims on every stored fixture, from the hand-written definitions of expected.json
(specs/011-claim-verifier spec US2, FR-020, SC-001, SC-002)."""

import json

import pytest

from conftest import FIXTURES, analyze_fixture
from graphora.mcp import from_store
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
