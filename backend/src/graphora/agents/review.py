"""The Reviewer: plain code that verifies claims, keeps hypotheses and routes (specs/012-agents research R4)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from graphora.agents.limits import MAX_REVISIONS, MAX_TOOL_CALLS
from graphora.agents.prompts import revision_task
from graphora.agents.state import AgentState, Hypothesis, Stated
from graphora.verify import Verdict, verify_served

if TYPE_CHECKING:
    from graphora.mcp.served import Served

Emit = Callable[..., Any]


def unique(claims: Sequence[Stated]) -> list[Stated]:
    """First occurrence of each claim key, in order."""
    seen: set[str] = set()
    out = []
    for s in claims:
        if s.key not in seen:
            seen.add(s.key)
            out.append(s)
    return out


def review(state: AgentState, served: Served, emit: Emit) -> dict[str, Any]:
    """Verify this round's new claims in one call, update hypotheses, choose `revise` or `answer`."""
    rnd = state.get("round", 0)
    verdicts: dict[str, Verdict] = dict(state.get("verdicts") or {})
    current = unique([s for s in state.get("claims") or () if s.round == rnd])
    new = [s for s in current if s.key not in verdicts]
    for s, v in zip(new, verify_served([s.claim for s in new], served), strict=True):
        verdicts[s.key] = v
        emit("verdict", key=s.key, cite=s.claim.cite(), status=v.status, reason=v.reason, hint=v.hint)

    hypotheses = list(state.get("hypotheses") or ())
    by_key = {h.key: n for n, h in enumerate(hypotheses)}
    for s in current:
        if s.revises is not None and verdicts[s.key].status != "rejected":
            hypotheses = [replace(h, open=False) if h.id == s.revises and h.open else h for h in hypotheses]
    rejected = []
    for s in current:
        v = verdicts[s.key]
        if v.status != "rejected":
            continue
        rejected.append(s.key)
        if s.key not in by_key:
            h = Hypothesis(f"h{len(hypotheses) + 1}", s.key, s.claim, v.reason or "invalid_claim", v.hint)
            by_key[s.key] = len(hypotheses)
            hypotheses.append(h)
            emit("hypothesis", key=h.key, cite=h.claim.cite(), reason=h.reason, hint=h.hint, detail=h.id)

    update: dict[str, Any] = {"verdicts": verdicts, "hypotheses": hypotheses, "route": "answer"}
    revisions = state.get("revisions", 0)
    open_now = [hypotheses[by_key[k]] for k in dict.fromkeys(rejected) if hypotheses[by_key[k]].open]
    if open_now and revisions < MAX_REVISIONS and state.get("tool_calls", 0) < MAX_TOOL_CALLS and not state.get("failed"):
        revisions += 1
        hypotheses = [replace(h, tries=h.tries + 1) if h.open else h for h in hypotheses]
        still_open = [h for h in hypotheses if h.open]
        update |= {
            "hypotheses": hypotheses,
            "route": "revise",
            "revisions": revisions,
            "round": rnd + 1,
            "task": revision_task(still_open, revisions),
        }
        emit("revision", detail=f"revision {revisions} of {MAX_REVISIONS}: {len(still_open)} claims")
    return update


def end_reason(state: AgentState) -> str:
    """The first that applies: stopped, model_failed, model_budget_spent, budget_spent, revisions_spent,
    no_claims, answered (data-model.md § EndReason)."""
    failed = state.get("failed")
    if failed in ("stopped", "model_failed", "model_budget_spent"):
        return failed
    if state.get("tool_calls", 0) >= MAX_TOOL_CALLS:
        return "budget_spent"
    if any(h.open for h in state.get("hypotheses") or ()) and state.get("revisions", 0) >= MAX_REVISIONS:
        return "revisions_spent"
    if not state.get("claims"):
        return "no_claims"
    return "answered"
