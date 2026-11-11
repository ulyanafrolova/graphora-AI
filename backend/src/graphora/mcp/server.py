"""Read-only MCP tools over one served snapshot (specs/006-mcp-server contracts/mcp-tools.md).

Tool names, descriptions and instructions are fixed text: content of the analyzed repository appears only in
results (research § R7). Every tool calls the graph query layer or the store; nothing is computed here."""

from __future__ import annotations

from importlib.metadata import version
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from graphora.graph import queries
from graphora.graph.results import Answer, Overview, render_text
from graphora.mcp.served import Served

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

INSTRUCTIONS = (
    "Graphora answers questions about the import graph of one analyzed snapshot: {where}.\n"
    "Facts come from code analysis, not guesses. Every link cites file:line. \"resolved\" = written in code, "
    "\"heuristic\" = likely, shown as (likely). Unresolved imports are never followed; the completeness note says "
    "how many there are. Start with graph_overview; use find_definitions to turn a symbol name into a file."
)

OVERVIEW = (
    "What the graph covers: snapshot, languages, analyzed and skipped files, unresolved imports. "
    "Call it first to learn which snapshot the answers are pinned to and what the graph cannot see."
)


def _result(value: Answer | Overview, extra: dict[str, Any] | None = None, heading: str = "") -> CallToolResult:
    """The answer document as structured content and `render_text` as text (research § R4)."""
    text = heading + render_text(value)
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=value.to_dict() | (extra or {}))


def _error(message: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


def create_server(served: Served) -> MCPServer:
    where = served.snapshot if served.repository is None else f"{served.snapshot} of {served.repository}"
    server = MCPServer("graphora", version=version("graphora"), instructions=INSTRUCTIONS.format(where=where))
    ix = served.index

    @server.tool(description=OVERVIEW, annotations=READ_ONLY)
    def graph_overview() -> CallToolResult:
        if served.repository is None:
            return _result(queries.overview(ix))
        return _result(queries.overview(ix), {"repository": served.repository}, f"repository {served.repository}\n")

    return server
