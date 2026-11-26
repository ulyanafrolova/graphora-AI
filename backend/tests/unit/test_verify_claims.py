"""Claim and verdict types (specs/011-claim-verifier data-model.md, contracts/verifier.md)."""

import json

import pytest

from graphora.verify import Check, Claim, Line, Step, Verdict, dumps, validate
from synthetic import edge

EXAMPLES = [
    {"kind": "dependency", "statement": "routes uses the auth service", "snapshot": "abc123",
     "steps": [{"path": "api/routes.py", "line": 3, "target": "auth/service.py", "name": "AuthService"}]},
    {"kind": "chain", "statement": "c.py is affected by a.py", "snapshot": "abc123",
     "steps": [{"path": "c.py", "line": 1, "target": "b.py"}, {"path": "b.py", "line": 2, "target": "a.py"}]},
    {"kind": "definition", "statement": "", "snapshot": "abc123", "path": "auth/service.py", "line": 12, "symbol": "AuthService"},
    {"kind": "mention", "statement": "", "snapshot": "abc123", "path": "auth/service.py", "line": 40, "symbol": "hash_password"},
    {"kind": "query", "statement": "3 direct dependents", "snapshot": "abc123",
     "question": "dependents", "target": "auth/service.py", "options": {}, "count": 3},
    {"kind": "query", "statement": "", "snapshot": "abc123",
     "question": "impact", "target": "a.py", "options": {"max_depth": 3}, "member": "c.py", "distance": 2},
    {"kind": "query", "statement": "", "snapshot": "abc123",
     "question": "key_files", "target": None, "options": {}, "member": "core.py", "rank": 5},
]


def dep(**step):
    return Claim("dependency", "", "s", steps=(Step(**({"path": "a.py", "line": 1, "target": "b.py"} | step)),))


def query(**fields):
    return Claim("query", "", "s", **({"question": "dependents", "target": "a.py", "count": 1} | fields))


@pytest.mark.parametrize("data", EXAMPLES)
def test_round_trip(data):
    claim = Claim.from_dict(data)
    assert claim.to_dict() == data
    assert validate(claim) is None


def test_to_dict_drops_none():
    assert "name" not in dep().to_dict()["steps"][0]
    assert set(dep().to_dict()) == {"kind", "statement", "snapshot", "steps"}


def test_from_dict_rejects_unknown_fields():
    with pytest.raises(ValueError):
        Claim.from_dict(EXAMPLES[0] | {"confidence": "high"})


def test_cite():
    assert Claim.from_dict(EXAMPLES[0]).cite() == "api/routes.py:3@abc123"
    assert Claim.from_dict(EXAMPLES[1]).cite() == "c.py:1@abc123"
    assert Claim.from_dict(EXAMPLES[2]).cite() == "auth/service.py:12@abc123"
    assert Claim.from_dict(EXAMPLES[4]).cite() is None


@pytest.mark.parametrize(
    "claim",
    [
        Claim("dependency", "", "s"),
        Claim("chain", "", "s"),
        Claim("definition", "", "s", line=1, symbol="A"),
        Claim("mention", "", "s", path="", line=1, symbol="A"),
    ],
)
def test_no_citation_comes_first(claim):
    assert validate(claim)[0] == "no_citation"


@pytest.mark.parametrize(
    "claim",
    [
        Claim("guess", "", "s", path="a.py", line=1, symbol="A"),
        Claim("dependency", "", "", steps=(Step("a.py", 1, "b.py"),)),
        dep(line=0),
        dep(line=True),
        dep(path=""),
        dep(target=""),
        dep(name=""),
        Claim("dependency", "", "s", steps=(Step("a.py", 1, "b.py"), Step("b.py", 1, "c.py"))),
        Claim("chain", "", "s", steps=(Step("a.py", 1, "b.py"),)),
        Claim("dependency", "", "s", steps=(Step("a.py", 1, "b.py"),), symbol="A"),
        Claim("definition", "", "s", path="a.py", line=0, symbol="A"),
        Claim("mention", "", "s", path="a.py", line=1, symbol=""),
        Claim("mention", "", "s", path="a.py", line=1, symbol="A", count=1),
        query(question="projects"),
        query(target=None),
        query(question="cycles", target="a.py"),
        query(options={"limit": 5}),
        query(options={"max_depth": 2}),
        query(count=None),
        query(member="b.py"),
        query(count=-1),
        query(count=None, member="b.py", distance=1),
        query(question="impact", count=None, member="b.py", distance=0),
        query(count=None, member="b.py", rank=3),
        query(question="key_files", target=None, count=None, member="b.py", rank=0),
        query(path="a.py"),
    ],
)
def test_invalid_claims(claim):
    reason, detail = validate(claim)
    assert reason == "invalid_claim" and detail


def test_query_options_allowed_per_question():
    assert validate(query(question="impact", count=None, member="b.py", options={"max_depth": 2, "level": "project"})) is None
    assert validate(query(options={"symbol": "A", "follow_barrels": True, "include_type_only": False})) is None
    assert validate(query(question="cycles", target=None, options={"level": "project"})) is None


def test_verdict_to_dict():
    e = edge("a.py", "b.py", 3, symbol="b")
    verified = Verdict("verified", (Check("edge", True, "1 edge"),), proof=(e, Line("a.py", 3, "import b")))
    d = verified.to_dict()
    assert d["fact"] is True
    assert d["checks"] == [{"name": "edge", "ok": True, "detail": "1 edge"}]
    assert d["proof"][0]["kind"] == "edge" and d["proof"][0]["line"] == 3 and d["proof"][0]["snippet_hash"]
    assert d["proof"][1] == {"kind": "line", "path": "a.py", "n": 3, "text": "import b"}
    assert set(d) == {"status", "fact", "checks", "proof"}

    rejected = Verdict("rejected", (Check("line", False, "no edge on line 5"),), "edge_not_on_line", "edge on line 3", step=2)
    d = rejected.to_dict()
    assert (d["fact"], d["reason"], d["hint"], d["step"], d["proof"]) == (False, "edge_not_on_line", "edge on line 3", 2, [])
    assert Verdict("heuristic", ()).fact is False


def test_dumps_is_canonical():
    verdicts = (Verdict("verified", (Check("edge", True, "1 edge"),)), Verdict("rejected", (), "no_edge"))
    out = dumps(verdicts)
    assert out == dumps(verdicts)
    assert out.endswith(b"\n")
    assert json.loads(out)[1]["reason"] == "no_edge"
