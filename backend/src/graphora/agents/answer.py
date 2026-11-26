"""The answer, built by code from verdicts, and the check of the model's summary (specs/012-agents research R7)."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable

from graphora.agents.prompts import REASON_TEXT, shown
from graphora.agents.review import unique
from graphora.agents.state import AgentState, Answer, Item
from graphora.verify import Claim

UNRELATED = "I can only answer questions about the analyzed snapshot; nothing could be verified."
NOTHING = "Nothing about the question could be verified."

_LABELS = {
    "dependencies": "direct dependencies",
    "dependents": "direct dependents",
    "impact": "files in its impact",
    "neighbors": "neighbors",
    "cycles": "import cycles",
    "key_files": "key files",
}
_EXTENSIONS = (
    "py|pyi|ts|tsx|js|jsx|mjs|cjs|mts|cts|cs|csproj|sln|props|targets|json|toml|cfg|ini|md|txt|yml|yaml|html|css|vue"
)
_PATH = re.compile(r"[\w.\-]*(?:/[\w.\-]+)+|[\w\-][\w.\-]*\.(?:" + _EXTENSIONS + r")\b")
_PATH_LINE = re.compile(r"((?:[\w.\-]+/)*[\w.\-]+):(\d+)")


def cite(claim: Claim) -> str:
    """`path:line@snapshot`, or `<question>(<target>)@<snapshot>` for a query claim."""
    return claim.cite() or f"{claim.question}({claim.target or ''})@{claim.snapshot}"


def sentence(claim: Claim) -> str:
    """A fixed-template sentence from the claim's fields; the model's statement is never used."""
    if claim.kind == "dependency":
        s = claim.steps[0]
        name = f" (name `{s.name}`)" if s.name else ""
        return f"`{s.path}` imports `{shown(s.target)}`{name}"
    if claim.kind == "chain":
        files = [claim.steps[0].path] + [shown(s.target) for s in claim.steps]
        chain = " → ".join(f"`{f}`" for f in files)
        return f"import cycle: {chain}" if files[-1] == files[0] else f"`{files[0]}` depends on `{files[-1]}` through {chain}"
    if claim.kind == "definition":
        return f"`{claim.symbol}` is defined in `{claim.path}` at line {claim.line}"
    if claim.kind == "mention":
        return f"line {claim.line} of `{claim.path}` mentions `{claim.symbol}`"
    label = _LABELS.get(claim.question or "", claim.question or "results")
    if claim.count is not None:
        return f"`{claim.target}` has {claim.count} {label}" if claim.target else f"the snapshot has {claim.count} {label}"
    if claim.question == "key_files":
        return f"`{claim.member}` is among the {claim.rank} most depended-on files" if claim.rank else f"`{claim.member}` is a key file"
    distance = f" at distance {claim.distance}" if claim.distance is not None else ""
    return f"`{claim.member}` is among the {label} of `{claim.target}`{distance}"


def parts(state: AgentState) -> tuple[tuple[Item, ...], tuple[Item, ...], tuple[Item, ...]]:
    verdicts = state.get("verdicts") or {}
    facts, likely = [], []
    for s in unique(state.get("claims") or ()):
        v = verdicts.get(s.key)
        if v is None or v.status == "rejected":
            continue
        (facts if v.status == "verified" else likely).append(Item(sentence(s.claim), cite(s.claim), s.claim))
    hypotheses = [
        Item(sentence(h.claim), cite(h.claim), h.claim, h.reason, h.hint)
        for h in sorted(state.get("hypotheses") or (), key=lambda h: int(h.id[1:]))
        if h.open
    ]
    return tuple(facts), tuple(likely), tuple(hypotheses)


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def code_summary(state: AgentState, facts: tuple[Item, ...], likely: tuple[Item, ...], hypotheses: tuple[Item, ...]) -> str:
    evidence = state.get("evidence") or ()
    if not evidence and not state.get("claims"):
        return UNRELATED
    if not facts and not likely:
        if evidence and all(e.error for e in evidence):
            names = [e.args.get("target") or e.args.get("name") or e.args.get("path") for e in evidence]
            name = next((n for n in names if n), None)
            if name is not None:
                return f"`{name}` was not found in the snapshot; nothing could be verified."
        if not state.get("claims"):
            return NOTHING
    return (
        f"Verified: {_plural(len(facts), 'fact', 'facts')}, {_plural(len(likely), 'likely link', 'likely links')}, "
        f"{_plural(len(hypotheses), 'hypothesis', 'hypotheses')} (not proven)."
    )


def _files(claims: Iterable[Claim]) -> set[str]:
    out: set[str] = set()
    for c in claims:
        for s in c.steps:
            out |= {s.path, shown(s.target)}
        out |= {shown(x) for x in (c.path, c.target, c.member) if x}
    return out | {posixpath.basename(f) for f in out}


def _lines(claims: Iterable[Claim]) -> set[str]:
    out: set[str] = set()
    for c in claims:
        out |= {f"{s.path}:{s.line}" for s in c.steps}
        if c.path is not None:
            out.add(f"{c.path}:{c.line}")
    return out


def check_summary(text: str, facts: tuple[Item, ...], likely: tuple[Item, ...]) -> bool:
    """True when every path the summary names belongs to a fact or likely claim and every `path:line` is a fact
    citation (FR-014). Names are checked, not wording."""
    fact_lines = _lines(i.claim for i in facts)
    for m in _PATH_LINE.finditer(text):
        if ("/" in m.group(1) or _PATH.fullmatch(m.group(1))) and f"{m.group(1)}:{m.group(2)}" not in fact_lines:
            return False
    files = _files(i.claim for i in facts + likely)
    for m in _PATH.finditer(_PATH_LINE.sub(lambda m: m.group(1), text)):
        token = m.group(0).strip(".-")
        if token and token not in files:
            return False
    return True


def build_answer(state: AgentState, summary: str | None, end: str) -> Answer:
    facts, likely, hypotheses = parts(state)
    use_model = summary is not None and check_summary(summary, facts, likely)
    return Answer(
        state["question"],
        state["snapshot"],
        facts,
        likely,
        hypotheses,
        summary.strip() if use_model and summary is not None else code_summary(state, facts, likely, hypotheses),
        "model" if use_model else "code",
        end,
        {
            "tool_calls": state.get("tool_calls", 0),
            "model_calls": state.get("model_calls", 0),
            "revisions": state.get("revisions", 0),
        },
    )


def summary_input(question: str, facts: tuple[Item, ...], likely: tuple[Item, ...]) -> str:
    lines = [f"Question: {question}", "", "Facts:"]
    lines += [f"- {i.text} ({i.cite})" for i in facts] or ["(none)"]
    lines += ["", "Likely:"]
    lines += [f"- {i.text} ({i.cite})" for i in likely] or ["(none)"]
    return "\n".join(lines)


def render_answer(answer: Answer) -> str:
    out = [f"Question: {answer.question}", "", "Facts"]
    out += [f"- {i.text} ({i.cite})" for i in answer.facts] or ["(none)"]
    out += ["", "Likely"]
    out += [f"- {i.text} ({i.cite}), likely" for i in answer.likely] or ["(none)"]
    out += ["", "Hypotheses (not proven)"]
    for i in answer.hypotheses:
        hint = f"; hint: {i.hint}" if i.hint else ""
        out.append(f"- {i.text} ({i.cite}): {REASON_TEXT.get(i.reason or '', i.reason)}{hint}")
    if not answer.hypotheses:
        out.append("(none)")
    out += ["", "Summary", answer.summary, "", f"snapshot {answer.snapshot} · ended: {answer.end}"]
    return "\n".join(out) + "\n"
