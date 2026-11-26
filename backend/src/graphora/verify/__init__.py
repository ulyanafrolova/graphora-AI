"""Deterministic claim verifier: claims checked against the graph and stored file text, no model
(specs/011-claim-verifier)."""

from collections.abc import Sequence

from graphora.graph.queries import GraphIndex
from graphora.verify.claims import Check, Claim, Line, Reason, Step, Verdict, dumps, validate
from graphora.verify.graph_checks import check_query, check_steps

__all__ = ["Check", "Claim", "Line", "Reason", "Step", "Verdict", "dumps", "validate", "verify"]


def verify(claims: Sequence[Claim], ix: GraphIndex, text: object | None = None) -> tuple[Verdict, ...]:
    """One verdict per claim, in claim order (contracts/verifier.md)."""
    return tuple(_verify(claim, ix) for claim in claims)


def _verify(claim: Claim, ix: GraphIndex) -> Verdict:
    problem = validate(claim)
    if problem is not None:
        reason, detail = problem
        return Verdict("rejected", (Check("claim", False, detail),), reason)
    snapshot = ix.doc.snapshot
    if claim.snapshot != snapshot:
        return Verdict("rejected", (Check("snapshot", False, claim.snapshot),), "snapshot_mismatch", f"checked snapshot {snapshot}")
    checks = [Check("snapshot", True, snapshot)]
    if claim.kind in ("dependency", "chain"):
        return check_steps(ix, claim, checks)
    if claim.kind == "query":
        return check_query(ix, claim, checks)
    checks.append(Check("text", False, "no file text"))
    return Verdict("rejected", tuple(checks), "text_unavailable")
