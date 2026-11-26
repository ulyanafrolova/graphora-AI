"""Claims built from every fixture's hand-written expected.json and queries.json (specs/011-claim-verifier
spec US1, FR-020, SC-001–SC-003)."""

import json
import subprocess
import sys
from functools import cache

import pytest

from conftest import FIXTURES, REPO_ROOT, analyze_fixture
from graphora.graph import queries
from graphora.verify import Claim, Step, verify

NAMES = sorted(p.name for p in FIXTURES.iterdir() if (p / "expected.json").is_file())
QUESTIONS = ("dependencies", "dependents", "impact", "neighbors", "cycles", "key_files")


@cache
def ix(name):
    return queries.index(analyze_fixture(name).doc)


def expected(name):
    return json.loads((FIXTURES / name / "expected.json").read_text(encoding="utf-8"))


def path(node_id):
    return node_id.split(":", 1)[1]


def dep(name, source, line, target, symbol=None, snapshot=None):
    snap = snapshot or ix(name).doc.snapshot
    return Claim("dependency", "", snap, steps=(Step(path(source), line, target, symbol),))


def check(name, claims):
    return verify(claims, ix(name))


def strongest(edges, e):
    same = [x for x in edges if (x["source"], x["target"], x["line"], x["symbol"]) == (e["source"], e["target"], e["line"], e["symbol"])]
    return "verified" if any(x["confidence"] == "resolved" for x in same) else "heuristic"


@pytest.mark.parametrize("name", NAMES)
def test_every_edge_verifies_as_its_confidence(name):
    edges = expected(name)["edges"]
    linked = [e for e in edges if e["confidence"] != "unresolved"]
    verdicts = check(name, [dep(name, e["source"], e["line"], e["target"], e["symbol"]) for e in linked])
    for e, v in zip(linked, verdicts, strict=True):
        assert v.status == strongest(linked, e), (e, v.to_dict())


@pytest.mark.parametrize("name", NAMES)
def test_unresolved_imports_never_verify(name):
    edges = [e for e in expected(name)["edges"] if e["confidence"] == "unresolved"]
    for e, v in zip(edges, check(name, [dep(name, e["source"], e["line"], e["target"]) for e in edges]), strict=True):
        assert v.status == "rejected", (e, v.to_dict())


@pytest.mark.parametrize("name", NAMES)
def test_changed_claims_are_rejected(name):
    edges = expected(name)["edges"]
    files = sorted(n for n in ix(name).nodes if n.startswith("file:"))
    unresolved_lines = {(e["source"], e["line"]) for e in edges if e["confidence"] == "unresolved"}
    for e in (e for e in edges if e["confidence"] == "resolved"):
        src, tgt, line = e["source"], e["target"], e["line"]
        cases = [
            (dep(name, src, 100000, tgt), "edge_not_on_line"),
            (dep(name, "file:missing/x.py", line, tgt), "file_not_in_snapshot"),
            (dep(name, src, line, tgt, snapshot="other"), "snapshot_mismatch"),
        ]
        other = next((f for f in files if f not in (src, tgt) and not ix(name).links.has_edge(src, f)), None)
        if other is not None:
            cases.append((dep(name, src, line, other), "import_unresolved" if (src, line) in unresolved_lines else "no_edge"))
        if e["symbol"] is not None:
            cases.append((dep(name, src, line, tgt, "NoSuchName"), "name_not_imported"))
        for (claim, reason), v in zip(cases, check(name, [c for c, _ in cases]), strict=True):
            assert (v.status, v.reason) == ("rejected", reason), (e, claim.to_dict(), v.to_dict())


def query_cases():
    for p in sorted(FIXTURES.glob("*/queries.json")):
        for i, entry in enumerate(json.loads(p.read_text(encoding="utf-8"))):
            if entry["question"] in QUESTIONS:
                yield pytest.param(p.parent.name, entry, id=f"{p.parent.name}-{i}-{entry['question']}")


def listed(entry):
    exp = entry["expected"]
    if entry["question"] == "cycles":
        return [(f, g.get("confidence", "resolved"), None) for g in exp["groups"] for f in g["files"]], exp["groups"]
    items = exp.get("items", []) + exp.get("incoming", []) + exp.get("outgoing", [])
    return [(i["node"], i.get("confidence", "resolved"), i.get("distance")) for i in items], items


def query(name, entry, **assertion):
    options = {k: v for k, v in entry["options"].items() if k != "limit"}
    return Claim("query", "", ix(name).doc.snapshot, question=entry["question"], target=entry["target"], options=options, **assertion)


@pytest.mark.parametrize(("name", "entry"), list(query_cases()))
def test_hand_written_answers_verify(name, entry):
    members, counted = listed(entry)
    total = entry["expected"].get("total", len(counted))
    status = "heuristic" if any(x.get("confidence") == "heuristic" for x in counted) else "verified"
    claims = [query(name, entry, count=total), query(name, entry, count=total + 1)]
    claims += [query(name, entry, member=node, distance=distance) for node, _, distance in members]
    outside = next((f for f in sorted(ix(name).nodes) if f.startswith("file:") and f not in {m for m, _, _ in members}
                    and path(f) != entry["target"]), None)
    if outside is not None:
        claims.append(query(name, entry, member=outside))
    verdicts = check(name, claims)
    assert verdicts[0].status == status, verdicts[0].to_dict()
    assert (verdicts[1].reason, verdicts[1].hint) == ("count_mismatch", f"actual {total}")
    for (node, _, _), v in zip(members, verdicts[2:], strict=False):
        expect = "verified" if any(c == "resolved" for m, c, _ in members if m == node) else "heuristic"
        if entry["question"] == "key_files":
            assert v.status != "rejected", (node, v.to_dict())
        else:
            assert v.status == expect, (node, v.to_dict())
    if outside is not None:
        assert verdicts[-1].reason == "not_in_result", verdicts[-1].to_dict()


SCRIPT = """
import json, sys
sys.path.insert(0, "tests")
from conftest import FIXTURES, REPO_ROOT, analyze_fixture
from graphora.graph import queries
from graphora.verify import Claim, Step, dumps, verify
name = sys.argv[1]
ix = queries.index(analyze_fixture(name).doc)
edges = json.loads((FIXTURES / name / "expected.json").read_text())["edges"]
claims = [Claim("dependency", "", ix.doc.snapshot, steps=(Step(e["source"].split(":", 1)[1], e["line"], e["target"], e["symbol"]),)) for e in edges]
claims += [Claim("query", "", ix.doc.snapshot, question="cycles", count=0)]
sys.stdout.buffer.write(dumps(verify(claims, ix)))
"""


def test_verdicts_are_identical_across_processes():
    """SC-004, FR-013."""
    runs = [
        subprocess.run([sys.executable, "-c", SCRIPT, "ts-app"], cwd=REPO_ROOT / "backend", capture_output=True, check=True).stdout
        for _ in range(2)
    ]
    assert runs[0] == runs[1]
    assert json.loads(runs[0])[0]["status"] in ("verified", "heuristic", "rejected")
