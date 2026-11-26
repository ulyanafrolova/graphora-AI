"""Hotspot claims (specs/014-hotspots contracts/verifier.md)."""

import dataclasses

import pytest

from graphora.graph.model import FileHistory, History, not_available
from graphora.graph.queries import index
from graphora.verify import Claim, dumps, verify
from synthetic import SNAP, edge, make_doc

EDGES = [edge("b.py", "a.py"), edge("c.py", "b.py"), edge("h.py", "g.py")]
FILES = {"a.py": (5, 1), "b.py": (8, 3), "g.py": (15, 4)}  # scores: g 15, a 10, b 8


def history(status="available"):
    return History(
        status, None, "f" * 40, "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "2025-02-01T00:00:00Z", 30, 0, 0,
        False, tuple(FileHistory(p, c, a) for p, (c, a) in sorted(FILES.items())),
    )


def doc(h=None, edges=EDGES):
    return dataclasses.replace(make_doc(edges), history=h or history())


def claim(**fields):
    return Claim("query", "", SNAP, question="hotspots", **fields)


def one(c, d=None):
    (verdict,) = verify([c], index(d or doc()))
    return verdict


def test_rank():
    v = one(claim(member="g.py", rank=1))
    assert (v.status, v.reason) == ("verified", None)
    assert [c.name for c in v.checks] == ["snapshot", "query", "member", "rank", "history"]
    v = one(claim(member="a.py", rank=1))
    assert (v.status, v.reason, v.hint) == ("rejected", "rank_mismatch", "rank 2")
    assert one(claim(member="a.py", rank=2)).status == "verified"


@pytest.mark.parametrize(
    ("member", "metric", "value"),
    [
        ("a.py", "commits", 5),
        ("a.py", "authors", 1),
        ("a.py", "score", 10),
        ("a.py", "transitive_dependents", 2),
        ("a.py", "direct_dependents", 1),
        ("g.py", "authors", 4),
    ],
)
def test_metric(member, metric, value):
    v = one(claim(member=member, metric=metric, value=value))
    assert v.status == "verified"
    assert v.checks[-2].name == "metric" and v.checks[-2].detail == f"{metric} {value}"
    wrong = one(claim(member=member, metric=metric, value=value + 1))
    assert (wrong.status, wrong.reason, wrong.hint) == ("rejected", "count_mismatch", f"actual {value}")


def test_rank_and_metric_together():
    assert one(claim(member="g.py", rank=1, metric="commits", value=15)).status == "verified"
    assert one(claim(member="g.py", rank=1, metric="commits", value=14)).reason == "count_mismatch"


def test_count():
    assert one(claim(count=3)).status == "verified"
    v = one(claim(count=4))
    assert (v.reason, v.hint) == ("count_mismatch", "actual 3")


def test_not_a_hotspot():
    assert one(claim(member="c.py", metric="commits", value=0)).reason == "not_in_result"
    v = one(claim(member="c.py", rank=3))
    assert (v.reason, v.hint) == ("rank_mismatch", "not ranked")
    assert one(claim(member="nope.py", rank=1)).reason == "target_not_found"


def test_history_not_available():
    v = one(claim(member="g.py", rank=1), doc(not_available("zip")))
    assert (v.status, v.reason, v.hint) == ("rejected", "history_unavailable", "zip")
    assert one(claim(count=0), doc(not_available("skipped"))).reason == "history_unavailable"


def test_partial_is_heuristic():
    v = one(claim(member="g.py", rank=1), doc(history("partial")))
    assert v.status == "heuristic" and not v.fact
    assert v.checks[-1].detail == "partial: 30 commits read"


def test_heuristic_dependent():
    edges = [edge("b.py", "a.py", confidence="heuristic"), edge("c.py", "b.py"), edge("h.py", "g.py")]
    assert one(claim(member="a.py", metric="commits", value=5), doc(edges=edges)).status == "heuristic"


@pytest.mark.parametrize(
    "fields",
    [
        {"member": "a.py", "metric": "commits"},
        {"member": "a.py", "value": 5},
        {"member": "a.py", "metric": "lines", "value": 5},
        {"member": "a.py", "metric": "commits", "value": -1},
        {"count": 3, "metric": "commits", "value": 3},
        {"member": "a.py", "rank": 1, "target": "a.py"},
        {"member": "a.py", "rank": 1, "options": {"symbol": "x"}},
    ],
)
def test_invalid(fields):
    v = one(claim(**fields))
    assert (v.status, v.reason) == ("rejected", "invalid_claim")


def test_metric_only_for_hotspots():
    v = one(Claim("query", "", SNAP, question="key_files", member="a.py", metric="commits", value=5))
    assert v.reason == "invalid_claim"


def test_json_round_trip_and_bytes():
    c = claim(member="g.py", rank=1, metric="commits", value=15)
    assert Claim.from_dict(c.to_dict()) == c
    assert dumps(verify([c], index(doc()))) == dumps(verify([c], index(doc())))
