"""The 011 agent tools as LangChain tools, per role, with run-wide citation ids (specs/012-agents research R3,
contracts/agents.md § Role prompts and tools)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import ValidationError

from graphora.agents.claims import claim_key
from graphora.agents.limits import MAX_CITATION_LINE, MAX_TOOL_MESSAGE_CHARS
from graphora.agents.state import Evidence
from graphora.tools import TOOLS, ToolResult, tools_for
from graphora.verify import Claim

if TYPE_CHECKING:
    from graphora.mcp.served import Served

ROLE_TOOLS: dict[str, tuple[str, ...]] = {
    "explorer": ("find_definitions", "read_lines", "dependents"),
    "analyst": ("dependents", "impact", "neighbors", "cycles"),
}
BUDGET_SPENT = "tool budget spent, write your result now"


class CitationIds:
    """Run-wide ids `c1, c2, …` in order of first appearance; the same claim keeps its id."""

    def __init__(self) -> None:
        self.by_key: dict[str, str] = {}
        self.claims: dict[str, Claim] = {}

    def add(self, claim: Claim) -> str:
        key = claim_key(claim)
        if key not in self.by_key:
            cid = f"c{len(self.by_key) + 1}"
            self.by_key[key] = cid
            self.claims[cid] = claim
        return self.by_key[key]


class RoleTools:
    """The bound StructuredTools of one role and the 011 functions behind them."""

    def __init__(self, role: str, served: Served) -> None:
        fns = tools_for(served)
        specs = {s.name: s for s in TOOLS}
        self.functions: dict[str, Callable[..., ToolResult]] = {n: fns[n] for n in ROLE_TOOLS[role] if n in fns}
        self.tools: dict[str, StructuredTool] = {
            n: StructuredTool.from_function(f, name=n, description=specs[n].description) for n, f in self.functions.items()
        }


def role_tools(role: str, served: Served) -> RoleTools:
    return RoleTools(role, served)


def citation_line(cid: str, claim: Claim) -> str:
    if claim.steps:
        line = f"[{cid}] {claim.cite()} → {' → '.join(s.target for s in claim.steps)}"
    elif claim.kind == "definition":
        line = f"[{cid}] {claim.cite()} defines {claim.symbol}"
    else:
        line = f"[{cid}] {claim.cite()} {claim.symbol}"
    if len(line) > MAX_CITATION_LINE:
        half = (MAX_CITATION_LINE - 1) // 2
        line = line[:half] + "…" + line[len(line) - (MAX_CITATION_LINE - 1 - half) :]
    return line


def citation_block(ids: list[str], claims: dict[str, Claim], room: int) -> str:
    """`citations:` and one line per id, cut by whole lines to fit `room` characters."""
    if not ids:
        return ""
    lines = ["citations:"]
    used = len(lines[0]) + 1
    for n, cid in enumerate(ids):
        line = citation_line(cid, claims[cid])
        rest = len(ids) - n - 1
        tail = len(f"(… {rest} more citations)") + 1 if rest else 0
        if used + len(line) + 1 + tail > room:
            lines.append(f"(… {len(ids) - n} more citations)")
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines) + "\n"


def _error(call: dict[str, Any], role: str, message: str) -> tuple[ToolMessage, Evidence]:
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    text = f"error: {message}"
    msg = ToolMessage(content=text, tool_call_id=call.get("id") or "", name=call.get("name") or "")
    return msg, Evidence(role, call.get("name") or "", dict(sorted(args.items())), error=message)


def refuse(call: dict[str, Any], role: str) -> tuple[ToolMessage, Evidence]:
    return _error(call, role, BUDGET_SPENT)


def run_tool_call(call: dict[str, Any], tools: RoleTools, ids: CitationIds, role: str) -> tuple[ToolMessage, Evidence]:
    """Validate the call, run the 011 function and append the citation block; nothing runs on bad input."""
    name = call.get("name") or ""
    args = call.get("args")
    if name not in tools.tools:
        return _error(call, role, f"unknown tool: {name}; available: {', '.join(tools.tools)}")
    if not isinstance(args, dict):
        return _error(call, role, f"arguments of {name} are not a JSON object")
    schema = tools.tools[name].args_schema
    extra = sorted(set(args) - set(schema.model_fields))
    if extra:
        return _error(call, role, f"unknown arguments for {name}: {', '.join(extra)}")
    try:
        valid = schema.model_validate(args)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or name
        return _error(call, role, f"invalid arguments for {name}: {where}: {first['msg']}")
    result = tools.functions[name](**{k: getattr(valid, k) for k in args})
    cited = [ids.add(c) for c in result.citations]
    block = citation_block(cited, ids.claims, MAX_TOOL_MESSAGE_CHARS - len(result.text))
    msg = ToolMessage(content=result.text + block, tool_call_id=call.get("id") or "", name=name)
    evidence = Evidence(role, name, dict(sorted(args.items())), tuple(cited), result.cut, result.error)
    return msg, evidence
