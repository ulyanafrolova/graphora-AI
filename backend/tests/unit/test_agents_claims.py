"""The Analyst's claims reply → 011 claims (specs/012-agents data-model.md § ClaimsReply, tasks T006)."""

from graphora.agents.claims import ClaimItem, ClaimsReply, claim_key, to_stated
from graphora.verify import Claim, Step

SNAP = "snap"
C1 = Claim("dependency", "", SNAP, steps=(Step("api/routes.py", 1, "auth/service.py", "AuthService"),))
C2 = Claim("definition", "", SNAP, path="auth/service.py", line=1, symbol="AuthService")
CITES = {"c1": C1, "c2": C2}


def stated(*items, open_ids=()):
    return to_stated(ClaimsReply(claims=list(items)), CITES, SNAP, 0, set(open_ids))


def test_three_forms():
    out, invalid = stated(
        ClaimItem(statement="routes use the service", cite="c1"),
        ClaimItem(statement="3 dependents", question="dependents", target="auth/service.py", count=3),
        ClaimItem(statement="cli imports it", path="cli.py", line=3, target="auth/service.py", name="AuthService"),
    )
    assert invalid == []
    assert out[0].claim.statement == "routes use the service" and out[0].claim.steps == C1.steps
    assert out[1].claim == Claim("query", "3 dependents", SNAP, question="dependents", target="auth/service.py", count=3)
    assert out[2].claim.steps == (Step("cli.py", 3, "auth/service.py", "AuthService"),)
    assert all(s.round == 0 and s.revises is None for s in out)


def test_snapshot_is_always_the_runs():
    other = {"c1": Claim("dependency", "", "other", steps=C1.steps)}
    out, _ = to_stated(ClaimsReply(claims=[ClaimItem(cite="c1")]), other, SNAP, 1, set())
    assert out[0].claim.snapshot == SNAP and out[0].round == 1


def test_invalid_items_are_dropped_with_a_reason():
    out, invalid = stated(
        ClaimItem(statement="nothing"),
        ClaimItem(cite="c1", question="dependents"),
        ClaimItem(cite="c9"),
        ClaimItem(cite="x1"),
        ClaimItem(path="a.py", target="b.py"),
        ClaimItem(cite="c1", revises="hyp1"),
        ClaimItem(cite="c2"),
    )
    assert [s.claim.kind for s in out] == ["definition"]
    assert [n for n, _ in invalid] == [1, 2, 3, 4, 5, 6]
    assert dict(invalid)[1] == "fits none of the claim forms" and dict(invalid)[3] == "unknown citation id"


def test_more_than_twenty_claims():
    out, invalid = stated(*[ClaimItem(cite="c1") for _ in range(22)])
    assert len(out) == 20 and [n for n, _ in invalid] == [21, 22]


def test_revises_only_open_hypotheses():
    out, _ = stated(ClaimItem(cite="c1", revises="h1"), ClaimItem(cite="c2", revises="h2"), open_ids={"h1"})
    assert [s.revises for s in out] == ["h1", None]


def test_claim_key_ignores_statement():
    a = Claim("dependency", "one", SNAP, steps=C1.steps)
    b = Claim("dependency", "two", SNAP, steps=C1.steps)
    assert claim_key(a) == claim_key(b) != claim_key(C2)
    assert "statement" not in claim_key(a)
