"""Dependency, chain and query result claims, checked against the graph only (specs/011-claim-verifier
research § R5, R7). Targets, symbols and answers come from the graph query layer."""

from __future__ import annotations

from graphora.graph import queries
from graphora.graph.model import Edge
from graphora.graph.results import Answer, Item, Link, weakest
from graphora.graph.serialize import edge_sort_key
from graphora.verify.claims import Check, Claim, Reason, Step, Verdict

_SOURCES = ("file:", "project:", "solution:")
_NOT_ANALYZED = {"not_in_snapshot": "file_not_in_snapshot", "invalid_path": "invalid_claim", "ambiguous": "invalid_claim"}
_ASK = {
    "dependencies": queries.dependencies,
    "dependents": queries.dependents,
    "impact": queries.impact,
    "neighbors": queries.neighbors,
    "cycles": queries.cycles,
    "key_files": queries.key_files,
    "hotspots": queries.hotspots,
}


class _Rejected(Exception):
    def __init__(self, reason: Reason, hint: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.hint = hint


def _lines(lines: list[int]) -> str:
    unique = sorted(set(lines))
    return f"edge on line {unique[0]}" if len(unique) == 1 else f"edges on lines {', '.join(map(str, unique))}"


def _step(ix: queries.GraphIndex, step: Step, checks: list[Check], prefix: str) -> tuple[str, str, tuple[Edge, ...], str]:
    """Source id, target id, the proving edges and their status; raises _Rejected at the first failed check."""

    def failed(name: str, detail: str, reason: Reason, hint: str | None = None) -> _Rejected:
        checks.append(Check(name, False, prefix + detail))
        return _Rejected(reason, hint)

    try:
        source = queries.resolve(ix, step.path)
    except queries.NodeNotFound as exc:
        raise failed("source", exc.message, _NOT_ANALYZED.get(exc.status, "file_not_analyzed")) from None
    if not source.startswith(_SOURCES):
        raise failed("source", f"{source} is not a file, project or solution", "invalid_claim")
    checks.append(Check("source", True, prefix + source))

    try:
        target = queries.resolve(ix, step.target)
    except queries.NodeNotFound as exc:
        raise failed("target", exc.message, "target_not_found", exc.message) from None
    checks.append(Check("target", True, prefix + target))

    edges: tuple[Edge, ...] = ix.links.edges[source, target]["edges"] if ix.links.has_edge(source, target) else ()
    if not edges:
        if any(e.line == step.line for e in ix.unresolved.get(source, ())):
            raise failed("edge", f"import on line {step.line} is unresolved", "import_unresolved")
        raise failed("edge", f"no edge from {source} to {target}", "no_edge")
    checks.append(Check("edge", True, prefix + (f"{len(edges)} edge" if len(edges) == 1 else f"{len(edges)} edges")))

    on_line = tuple(e for e in edges if e.line == step.line)
    if not on_line:
        raise failed("line", f"no edge on line {step.line}", "edge_not_on_line", _lines([e.line for e in edges]))
    type_only = " (type-only)" if all(e.type_only for e in on_line) else ""
    checks.append(Check("line", True, f"{prefix}line {step.line}{type_only}"))

    if step.name is not None:
        named = tuple(e for e in on_line if queries.matches_symbol(e, step.name))
        if not named:
            names = sorted({n for e in on_line for n in (e.symbol, e.alias) if n is not None})
            hint = f"imported on line {step.line}: {', '.join(names) or '(no names)'}"
            raise failed("name", f"{step.name} is not imported on line {step.line}", "name_not_imported", hint)
        on_line = named
        checks.append(Check("name", True, prefix + step.name))

    status = "verified" if any(e.confidence == "resolved" for e in on_line) else "heuristic"
    return source, target, tuple(sorted(on_line, key=edge_sort_key)), status


def check_steps(ix: queries.GraphIndex, claim: Claim, checks: list[Check]) -> Verdict:
    """A dependency claim, or a chain taking its weakest step (FR-008, FR-009)."""
    proof: list[Edge] = []
    statuses: list[str] = []
    previous: str | None = None
    for n, step in enumerate(claim.steps, start=1):
        prefix = f"step {n}: " if claim.kind == "chain" else ""
        at = n if claim.kind == "chain" else None
        try:
            source, target, edges, status = _step(ix, step, checks, prefix)
        except _Rejected as exc:
            return Verdict("rejected", tuple(checks), exc.reason, exc.hint, at)
        if previous is not None and source != previous:
            checks.append(Check("claim", False, f"{prefix}starts at {source}, not at {previous}"))
            return Verdict("rejected", tuple(checks), "invalid_claim", None, at)
        previous = target
        proof += edges
        statuses.append("resolved" if status == "verified" else "heuristic")
    status = "verified" if weakest(statuses) == "resolved" else "heuristic"
    return Verdict(status, tuple(checks), proof=tuple(proof))


def _chain_edges(chain: tuple[Link, ...]) -> tuple[Edge, ...]:
    return tuple(sorted({e for link in chain for e in link.edges + link.via}, key=edge_sort_key))


def _found(answer: Answer, member: str) -> tuple[str, int | None, tuple[Edge, ...]] | None:
    """Status, distance and proof of the member in the answer, or None."""
    if answer.question == "cycles":
        for g in answer.groups or ():
            if member in g.files:
                return g.confidence, None, _chain_edges(g.cycle)
        return None
    items = [i for i in (answer.items or ()) + (answer.incoming or ()) + (answer.outgoing or ()) if i.node == member]
    if not items:
        return None
    best = next((i for i in items if i.confidence == "resolved"), items[0])
    return best.confidence, best.distance, _chain_edges(best.chain)


def _counted(answer: Answer) -> list[str]:
    if answer.question == "cycles":
        return [g.confidence for g in answer.groups or ()]
    items: tuple[Item, ...] = (answer.items or ()) + (answer.incoming or ()) + (answer.outgoing or ())
    return [i.confidence for i in items]


def check_query(ix: queries.GraphIndex, claim: Claim, checks: list[Check]) -> Verdict:
    """Re-run the question with the claim's options and no limit, then compare (FR-012a)."""
    history = ix.doc.history
    if claim.question == "hotspots" and history.status == "not_available":
        checks.append(Check("history", False, f"not available: {history.reason}"))
        return Verdict("rejected", tuple(checks), "history_unavailable", history.reason)
    ask = _ASK[claim.question]
    args = () if claim.target is None else (claim.target,)
    try:
        answer = ask(ix, *args, **claim.options, limit=None)
    except queries.NodeNotFound as exc:
        checks.append(Check("query", False, exc.message))
        return Verdict("rejected", tuple(checks), "target_not_found", exc.message)
    except (ValueError, TypeError) as exc:
        checks.append(Check("query", False, str(exc)))
        return Verdict("rejected", tuple(checks), "invalid_claim")
    checks.append(Check("query", True, f"{claim.question} total {answer.total}"))
    if claim.question == "hotspots":
        return _hotspot(ix, claim, answer, checks)

    if claim.count is not None:
        if answer.total != claim.count:
            checks.append(Check("count", False, f"{claim.count} != {answer.total}"))
            return Verdict("rejected", tuple(checks), "count_mismatch", f"actual {answer.total}")
        checks.append(Check("count", True, str(claim.count)))
        status = "heuristic" if "heuristic" in _counted(answer) else "verified"
        return Verdict(status, tuple(checks))

    try:
        member = queries.resolve(ix, claim.member)
    except queries.NodeNotFound as exc:
        checks.append(Check("member", False, exc.message))
        return Verdict("rejected", tuple(checks), "target_not_found", exc.message)
    found = _found(answer, member)
    if claim.question == "key_files":
        return _rank(ix, claim, member, answer, checks)
    if found is None:
        checks.append(Check("member", False, f"{member} not in the answer"))
        return Verdict("rejected", tuple(checks), "not_in_result")
    confidence, distance, proof = found
    if claim.distance is not None and distance != claim.distance:
        checks.append(Check("member", False, f"{member} at distance {distance}, not {claim.distance}"))
        return Verdict("rejected", tuple(checks), "not_in_result", f"at distance {distance}")
    checks.append(Check("member", True, member if distance is None else f"{member} at distance {distance}"))
    return Verdict("verified" if confidence == "resolved" else "heuristic", tuple(checks), proof=proof)


def _rank(ix: queries.GraphIndex, claim: Claim, member: str, answer: Answer, checks: list[Check]) -> Verdict:
    ranked = [i.node for i in answer.items or ()]
    if member not in ranked:
        checks.append(Check("member", False, f"{member} is not ranked"))
        if claim.rank is not None:
            return Verdict("rejected", tuple(checks), "rank_mismatch", "not ranked")
        return Verdict("rejected", tuple(checks), "not_in_result")
    position = ranked.index(member) + 1
    if claim.rank is not None and position > claim.rank:
        checks.append(Check("rank", False, f"{member} at rank {position}, not within {claim.rank}"))
        return Verdict("rejected", tuple(checks), "rank_mismatch", f"rank {position}")
    checks.append(Check("rank", True, f"{member} at rank {position}"))
    include_type_only = claim.options.get("include_type_only", True)
    dependents = queries.impact(ix, member, include_type_only=include_type_only).items or ()
    status = "heuristic" if any(i.confidence == "heuristic" for i in dependents) else "verified"
    return Verdict(status, tuple(checks))


def _hotspot(ix: queries.GraphIndex, claim: Claim, answer: Answer, checks: list[Check]) -> Verdict:
    """Count, rank and metric claims on hotspots (014 contracts/verifier.md)."""
    history = ix.doc.history
    heuristic = history.status == "partial"
    if claim.count is not None:
        if answer.total != claim.count:
            checks.append(Check("count", False, f"{claim.count} != {answer.total}"))
            return Verdict("rejected", tuple(checks), "count_mismatch", f"actual {answer.total}")
        checks.append(Check("count", True, str(claim.count)))
    else:
        try:
            member = queries.resolve(ix, claim.member)
        except queries.NodeNotFound as exc:
            checks.append(Check("member", False, exc.message))
            return Verdict("rejected", tuple(checks), "target_not_found", exc.message)
        ranked = [i.node for i in answer.items or ()]
        if member not in ranked:
            checks.append(Check("member", False, f"{member} is not a hotspot"))
            if claim.rank is not None:
                return Verdict("rejected", tuple(checks), "rank_mismatch", "not ranked")
            return Verdict("rejected", tuple(checks), "not_in_result")
        checks.append(Check("member", True, member))
        position = ranked.index(member) + 1
        if claim.rank is not None:
            if position > claim.rank:
                checks.append(Check("rank", False, f"{member} at rank {position}, not within {claim.rank}"))
                return Verdict("rejected", tuple(checks), "rank_mismatch", f"rank {position}")
            checks.append(Check("rank", True, f"{member} at rank {position}"))
        if claim.metric is not None:
            actual = getattr((answer.items or ())[position - 1], claim.metric)
            if actual != claim.value:
                checks.append(Check("metric", False, f"{claim.metric} {claim.value} != {actual}"))
                return Verdict("rejected", tuple(checks), "count_mismatch", f"actual {actual}")
            checks.append(Check("metric", True, f"{claim.metric} {claim.value}"))
        include_type_only = claim.options.get("include_type_only", True)
        dependents = queries.impact(ix, member, include_type_only=include_type_only).items or ()
        heuristic = heuristic or any(i.confidence == "heuristic" for i in dependents)
    note = f"partial: {history.commits_read} commits read" if history.status == "partial" else history.status
    checks.append(Check("history", True, note))
    return Verdict("heuristic" if heuristic else "verified", tuple(checks))
