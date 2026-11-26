"""Claims, verdicts and their JSON (specs/011-claim-verifier data-model.md, contracts/verifier.md)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field, fields
from typing import Any, Literal

from graphora.graph.model import Edge
from graphora.graph.serialize import _edge_dict

Kind = Literal["dependency", "chain", "definition", "mention", "query"]
Status = Literal["verified", "heuristic", "rejected"]
Reason = Literal[
    "invalid_claim",
    "no_citation",
    "snapshot_mismatch",
    "file_not_in_snapshot",
    "file_not_analyzed",
    "target_not_found",
    "no_edge",
    "import_unresolved",
    "edge_not_on_line",
    "name_not_imported",
    "text_unavailable",
    "line_out_of_range",
    "symbol_not_on_line",
    "definition_not_in_graph",
    "count_mismatch",
    "not_in_result",
    "rank_mismatch",
    "history_unavailable",
]

KINDS = ("dependency", "chain", "definition", "mention", "query")
ALLOWED_OPTIONS: dict[str, frozenset[str]] = {
    "dependencies": frozenset({"include_type_only", "level"}),
    "dependents": frozenset({"include_type_only", "follow_barrels", "symbol", "level"}),
    "impact": frozenset({"include_type_only", "follow_barrels", "max_depth", "level"}),
    "neighbors": frozenset({"include_type_only"}),
    "cycles": frozenset({"include_type_only", "level"}),
    "key_files": frozenset({"include_type_only"}),
    "hotspots": frozenset({"include_type_only"}),
}
METRICS = ("commits", "authors", "score", "transitive_dependents", "direct_dependents")
_STEP_KINDS = ("dependency", "chain")
_TEXT_KINDS = ("definition", "mention")
_TEXT_FIELDS = ("path", "line", "symbol")
_QUERY_FIELDS = ("question", "target", "count", "member", "distance", "rank", "metric", "value")


@dataclass(frozen=True)
class Step:
    path: str
    line: int
    target: str
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none({"path": self.path, "line": self.line, "target": self.target, "name": self.name})


@dataclass(frozen=True)
class Claim:
    kind: str
    statement: str
    snapshot: str
    steps: tuple[Step, ...] = ()
    path: str | None = None
    line: int | None = None
    symbol: str | None = None
    question: str | None = None
    target: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    count: int | None = None
    member: str | None = None
    distance: int | None = None
    rank: int | None = None
    metric: str | None = None  # 014: hotspots only, with value
    value: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Claim:
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"unknown claim fields: {', '.join(unknown)}")
        values = dict(data)
        values["steps"] = tuple(Step(**s) for s in data.get("steps", ()))
        values["options"] = dict(data.get("options") or {})
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "statement": self.statement, "snapshot": self.snapshot}
        if self.steps:
            out["steps"] = [s.to_dict() for s in self.steps]
        for name in _TEXT_FIELDS + _QUERY_FIELDS:
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        if self.kind == "query":
            out["target"] = self.target
            out["options"] = dict(self.options)
        return out

    def cite(self) -> str | None:
        """`path:line@snapshot` of the first citation; None for a query claim."""
        if self.steps:
            return f"{self.steps[0].path}:{self.steps[0].line}@{self.snapshot}"
        if self.path is not None:
            return f"{self.path}:{self.line}@{self.snapshot}"
        return None


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class Line:
    path: str
    n: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "line", "path": self.path, "n": self.n, "text": self.text}


@dataclass(frozen=True)
class Verdict:
    status: Status
    checks: tuple[Check, ...]
    reason: Reason | None = None
    hint: str | None = None
    step: int | None = None
    proof: tuple[Edge | Line, ...] = ()

    @property
    def fact(self) -> bool:
        """Only a verified claim may be stated as a fact (FR-005)."""
        return self.status == "verified"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": self.status,
            "fact": self.fact,
            "checks": [c.to_dict() for c in self.checks],
            "proof": [p.to_dict() if isinstance(p, Line) else {"kind": "edge"} | _edge_dict(p) for p in self.proof],
        }
        return out | _drop_none({"reason": self.reason, "hint": self.hint, "step": self.step})


def dumps(verdicts: Iterable[Verdict]) -> bytes:
    text = json.dumps([v.to_dict() for v in verdicts], sort_keys=True, ensure_ascii=False, indent=2)
    return (text + "\n").encode("utf-8")


def _drop_none(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def _is_line(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and value != ""


def validate(claim: Claim) -> tuple[Reason, str] | None:
    """`no_citation` or `invalid_claim` with a short detail, or None for a well-formed claim (data-model.md)."""
    if claim.kind in _STEP_KINDS and not claim.steps:
        return "no_citation", "no steps"
    if claim.kind in _TEXT_KINDS and not claim.path:
        return "no_citation", "no path"
    problem = _problem(claim)
    return None if problem is None else ("invalid_claim", problem)


def _problem(claim: Claim) -> str | None:
    if claim.kind not in KINDS:
        return f"unknown kind: {claim.kind}"
    if not _is_text(claim.snapshot):
        return "snapshot is empty"
    present = {name for name in _TEXT_FIELDS + _QUERY_FIELDS if getattr(claim, name) is not None}
    if claim.options:
        present.add("options")
    if claim.steps:
        present.add("steps")
    own = {"dependency": {"steps"}, "chain": {"steps"}, "definition": set(_TEXT_FIELDS), "mention": set(_TEXT_FIELDS)}
    allowed = own.get(claim.kind, set(_QUERY_FIELDS) | {"options"})
    if present - allowed:
        return f"fields not used by {claim.kind}: {', '.join(sorted(present - allowed))}"

    if claim.kind in _STEP_KINDS:
        if claim.kind == "dependency" and len(claim.steps) != 1:
            return "a dependency has exactly one step"
        if claim.kind == "chain" and len(claim.steps) < 2:
            return "a chain has at least two steps"
        for n, s in enumerate(claim.steps, start=1):
            if not (_is_text(s.path) and _is_line(s.line) and _is_text(s.target)) or (s.name is not None and not _is_text(s.name)):
                return f"step {n} needs a path, a line of 1 or more, a target and a non-empty name if given"
        return None
    if claim.kind in _TEXT_KINDS:
        if not (_is_text(claim.path) and _is_line(claim.line) and _is_text(claim.symbol)):
            return "needs a path, a line of 1 or more and a symbol"
        return None
    return _query_problem(claim)


def _query_problem(claim: Claim) -> str | None:
    q = claim.question
    if q not in ALLOWED_OPTIONS:
        return f"unknown question: {q}"
    if q in ("cycles", "key_files", "hotspots"):
        if claim.target is not None:
            return f"{q} takes no target"
    elif not _is_text(claim.target):
        return f"{q} needs a target"
    extra = sorted(set(claim.options) - ALLOWED_OPTIONS[q])
    if extra:
        return f"options not allowed for {q}: {', '.join(extra)}"
    if (claim.count is None) == (claim.member is None):
        return "give exactly one of count or member"
    if claim.count is not None and not (isinstance(claim.count, int) and not isinstance(claim.count, bool) and claim.count >= 0):
        return "count must be 0 or more"
    if claim.member is not None and not _is_text(claim.member):
        return "member is empty"
    if claim.distance is not None and (q != "impact" or claim.member is None or not _is_line(claim.distance)):
        return "distance is 1 or more, with member, for impact only"
    if claim.rank is not None and (q not in ("key_files", "hotspots") or claim.member is None or not _is_line(claim.rank)):
        return "rank is 1 or more, with member, for key_files and hotspots only"
    if (claim.metric is None) != (claim.value is None):
        return "metric and value go together"
    if claim.metric is not None:
        whole = isinstance(claim.value, int) and not isinstance(claim.value, bool)
        if q != "hotspots" or claim.member is None or claim.metric not in METRICS or not whole or claim.value < 0:
            return f"metric is one of {', '.join(METRICS)}, with member and a value of 0 or more, for hotspots only"
    return None
