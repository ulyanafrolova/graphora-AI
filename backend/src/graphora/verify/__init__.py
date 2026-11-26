"""Deterministic claim verifier: claims checked against the graph and stored file text, no model
(specs/011-claim-verifier)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from graphora.graph.queries import GraphIndex
from graphora.verify.claims import Check, Claim, Line, Reason, Step, Verdict, dumps, validate
from graphora.verify.graph_checks import check_query, check_steps
from graphora.verify.text_checks import Cached, TextSource, check_text, store_text

if TYPE_CHECKING:
    from graphora.mcp.served import Served

__all__ = [
    "Check",
    "Claim",
    "Line",
    "Reason",
    "Step",
    "TextSource",
    "Verdict",
    "dumps",
    "store_text",
    "validate",
    "verify",
    "verify_served",
]


def verify(claims: Sequence[Claim], ix: GraphIndex, text: TextSource | None = None) -> tuple[Verdict, ...]:
    """One verdict per claim, in claim order (contracts/verifier.md)."""
    cached = None if text is None else Cached(text)
    return tuple(_verify(claim, ix, cached) for claim in claims)


def verify_served(claims: Sequence[Claim], served: Served) -> tuple[Verdict, ...]:
    """With store text when the snapshot is served from the store."""
    text = None if served.store is None else store_text(served.store, served.repository, served.snapshot)
    return verify(claims, served.index, text)


def _verify(claim: Claim, ix: GraphIndex, text: TextSource | None) -> Verdict:
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
    return check_text(ix, claim, text, checks)
