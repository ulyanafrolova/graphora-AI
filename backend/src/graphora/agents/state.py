"""Shared agent state, answer and trace types (specs/012-agents data-model.md). Plain Python, no model."""

from __future__ import annotations

import json
import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, TypedDict

from graphora.verify import Claim, Verdict

Role = Literal["explorer", "analyst", "reviewer", "answer"]
EndReason = Literal["answered", "revisions_spent", "budget_spent", "model_budget_spent", "model_failed", "no_claims"]
END_REASONS: tuple[str, ...] = ("answered", "revisions_spent", "budget_spent", "model_budget_spent", "model_failed", "no_claims")
EventKind = Literal[
    "role_start", "tool_call", "claim", "claim_invalid", "verdict", "revision", "hypothesis", "summary", "end"
]


def _drop_none(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


@dataclass(frozen=True)
class Evidence:
    role: str
    tool: str
    args: dict[str, Any]
    citation_ids: tuple[str, ...] = ()
    cut: bool = False
    error: str | None = None


@dataclass(frozen=True)
class Stated:
    """A claim proposed by the Analyst; `key` identifies it without its statement (FR-012)."""

    claim: Claim
    key: str
    round: int
    revises: str | None = None


@dataclass(frozen=True)
class Hypothesis:
    id: str
    key: str
    claim: Claim
    reason: str
    hint: str | None = None
    tries: int = 0
    open: bool = True


@dataclass(frozen=True)
class TraceEvent:
    n: int
    kind: str
    role: str
    tool: str | None = None
    args: dict[str, Any] | None = None
    citation_ids: tuple[str, ...] | None = None
    cut: bool | None = None
    error: str | None = None
    key: str | None = None
    cite: str | None = None
    status: str | None = None
    reason: str | None = None
    hint: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out = _drop_none(
            {
                "n": self.n,
                "kind": self.kind,
                "role": self.role,
                "tool": self.tool,
                "args": self.args,
                "cut": self.cut,
                "error": self.error,
                "key": self.key,
                "cite": self.cite,
                "status": self.status,
                "reason": self.reason,
                "hint": self.hint,
                "detail": self.detail,
            }
        )
        if self.citation_ids is not None:
            out["citation_ids"] = list(self.citation_ids)
        return out


@dataclass(frozen=True)
class Item:
    """One line of an answer part: a fixed-template sentence, its citation and the claim behind it."""

    text: str
    cite: str
    claim: Claim
    reason: str | None = None
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(
            {"text": self.text, "cite": self.cite, "claim": self.claim.to_dict(), "reason": self.reason, "hint": self.hint}
        )


@dataclass(frozen=True)
class Answer:
    question: str
    snapshot: str
    facts: tuple[Item, ...]
    likely: tuple[Item, ...]
    hypotheses: tuple[Item, ...]
    summary: str
    summary_source: Literal["model", "code"]
    end: str
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "snapshot": self.snapshot,
            "facts": [i.to_dict() for i in self.facts],
            "likely": [i.to_dict() for i in self.likely],
            "hypotheses": [i.to_dict() for i in self.hypotheses],
            "summary": self.summary,
            "summary_source": self.summary_source,
            "end": self.end,
            "counts": dict(self.counts),
        }


@dataclass(frozen=True)
class Run:
    answer: Answer
    trace: tuple[TraceEvent, ...]
    error: str | None = None  # why the model failed, when `answer.end` is model_failed

    def to_dict(self) -> dict[str, Any]:
        out = {"answer": self.answer.to_dict(), "trace": [e.to_dict() for e in self.trace]}
        return out | ({"error": self.error} if self.error is not None else {})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, indent=2) + "\n"


class AgentState(TypedDict, total=False):
    """The LangGraph state shared by the roles (data-model.md § AgentState). Lists append, the rest replaces."""

    question: str
    snapshot: str
    evidence: Annotated[list[Evidence], operator.add]
    citations: dict[str, Claim]
    claims: Annotated[list[Stated], operator.add]
    verdicts: dict[str, Verdict]
    hypotheses: list[Hypothesis]
    task: str | None
    notes: str
    tool_calls: int
    model_calls: int
    revisions: int
    round: int
    failed: str | None
    route: str
    answer: Answer | None
    trace: Annotated[list[TraceEvent], operator.add]
