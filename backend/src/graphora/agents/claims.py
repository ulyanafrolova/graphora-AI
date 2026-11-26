"""The Analyst's structured claims reply and its conversion to 011 claims (specs/012-agents research R3,
data-model.md § ClaimsReply)."""

from __future__ import annotations

import json
import re
from dataclasses import replace

from pydantic import BaseModel, Field

from graphora.agents.limits import MAX_CLAIMS
from graphora.agents.state import Stated
from graphora.verify import Claim, Step

_CITE = re.compile(r"c\d+")
_HYPOTHESIS = re.compile(r"h\d+")


class ClaimItem(BaseModel):
    statement: str = Field("", description="the claim in one short sentence")
    cite: str | None = Field(None, description="a citation id from the tool results, like c3")
    question: str | None = Field(
        None, description="for a claim about a graph question result: dependencies, dependents, impact, neighbors, cycles or key_files"
    )
    target: str | None = Field(None, description="the file or package the question or dependency is about")
    count: int | None = Field(None, description="the number of items in the question's result")
    member: str | None = Field(None, description="a file the question's result contains")
    distance: int | None = Field(None, description="impact only: the member's distance")
    rank: int | None = Field(None, description="key_files only: the member is within this many first files")
    path: str | None = Field(None, description="for a dependency: the importing file")
    line: int | None = Field(None, description="for a dependency: the import line")
    name: str | None = Field(None, description="for a dependency: the imported name, if any")
    revises: str | None = Field(None, description="the id of the open hypothesis this claim corrects, like h1")


class ClaimsReply(BaseModel):
    claims: list[ClaimItem] = Field(default_factory=list)


def claim_key(claim: Claim) -> str:
    """Canonical JSON of the claim without its statement."""
    data = {k: v for k, v in claim.to_dict().items() if k != "statement"}
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _claim(item: ClaimItem, citations: dict[str, Claim], snapshot: str) -> Claim | str:
    forms = [item.cite is not None, item.question is not None, item.path is not None or item.line is not None]
    if sum(forms) == 0:
        return "fits none of the claim forms"
    if sum(forms) > 1:
        return "mixes claim forms"
    if item.cite is not None:
        if not _CITE.fullmatch(item.cite) or item.cite not in citations:
            return "unknown citation id"
        return replace(citations[item.cite], statement=item.statement, snapshot=snapshot)
    if item.question is not None:
        return Claim(
            "query",
            item.statement,
            snapshot,
            question=item.question,
            target=item.target,
            count=item.count,
            member=item.member,
            distance=item.distance,
            rank=item.rank,
        )
    if item.path is None or item.line is None or not item.target:
        return "a dependency needs path, line and target"
    return Claim("dependency", item.statement, snapshot, steps=(Step(item.path, item.line, item.target, item.name),))


def to_stated(
    reply: ClaimsReply, citations: dict[str, Claim], snapshot: str, round: int, open_ids: set[str]
) -> tuple[list[Stated], list[tuple[int, str]]]:
    """Claims in reply order, and (item number, reason) for the items that are not claims."""
    stated: list[Stated] = []
    invalid: list[tuple[int, str]] = []
    for n, item in enumerate(reply.claims, 1):
        if n > MAX_CLAIMS:
            invalid.append((n, f"more than {MAX_CLAIMS} claims"))
            continue
        if item.revises is not None and not _HYPOTHESIS.fullmatch(item.revises):
            invalid.append((n, "revises is not a hypothesis id"))
            continue
        claim = _claim(item, citations, snapshot)
        if isinstance(claim, str):
            invalid.append((n, claim))
            continue
        revises = item.revises if item.revises in open_ids else None
        stated.append(Stated(claim, claim_key(claim), round, revises))
    return stated, invalid
