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

DEFAULT_LIMIT, MAX_LIMIT = 50, 500

OVERVIEW = (
    "What the graph covers: snapshot, languages, analyzed and skipped files, unresolved imports. "
    "Call it first to learn which snapshot the answers are pinned to and what the graph cannot see."
)
_TARGET = "target is a file path like src/app.py, a node id, or an external package name like requests. "
_LISTS = f"limit (default {DEFAULT_LIMIT}, at most {MAX_LIMIT}) caps the items; total and truncated tell if more exist. "
_TYPE_ONLY = "include_type_only=false leaves out TypeScript `import type` links. "
_CONFIDENCE = (
    "Every link cites file:line; confidence is resolved (written in code) or heuristic (likely). "
    "The completeness note counts imports that could not be resolved."
)
DESCRIPTIONS = {
    "dependencies": "What a file imports, with the import lines; unresolved imports are listed separately. "
    + _TARGET + _TYPE_ONLY + _LISTS + _CONFIDENCE,
    "dependents": "Which files import this file or package, with the import lines; optionally only one imported "
    "name. " + _TARGET + "symbol keeps only imports of that name. follow_barrels=true also counts files that "
    "import the name through index.ts re-exports. " + _TYPE_ONLY + _LISTS + _CONFIDENCE,
    "impact": "Every file that depends on this file directly or through other files, nearest first, each with "
    "its chain of imports: what can break if the file changes. " + _TARGET + "max_depth stops the search at that "
    "distance; cut tells if it stopped early. follow_barrels=true sees through index.ts re-exports. "
    + _TYPE_ONLY + _LISTS + _CONFIDENCE,
    "neighbors": "A file's direct imports and the files that import it, in one answer. "
    + _TARGET + _TYPE_ONLY + "limit caps each of the two lists. " + _CONFIDENCE,
    "cycles": "Groups of files that import each other in a loop, each with one example cycle of import lines. "
    "A group marked type_only loops only through type imports and does not fail at run time. "
    + _TYPE_ONLY + _LISTS + _CONFIDENCE,
    "key_files": "The files most depended on, ranked by transitive and then direct dependents. "
    + _TYPE_ONLY + "limit (default 10, at most 500) caps the files.",
}


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

    def ask(question: Any, *target: str, limit: int, **options: Any) -> CallToolResult:
        if not 0 <= limit <= MAX_LIMIT:
            return _error(f"limit must be between 0 and {MAX_LIMIT}")
        try:
            return _result(question(ix, *target, limit=limit, **options))
        except queries.NodeNotFound as exc:
            return _error(exc.message)
        except ValueError as exc:
            return _error(str(exc))

    @server.tool(description=OVERVIEW, annotations=READ_ONLY)
    def graph_overview() -> CallToolResult:
        if served.repository is None:
            return _result(queries.overview(ix))
        return _result(queries.overview(ix), {"repository": served.repository}, f"repository {served.repository}\n")

    @server.tool(description=DESCRIPTIONS["dependencies"], annotations=READ_ONLY)
    def dependencies(target: str, include_type_only: bool = True, limit: int = DEFAULT_LIMIT) -> CallToolResult:
        return ask(queries.dependencies, target, include_type_only=include_type_only, limit=limit)

    @server.tool(description=DESCRIPTIONS["dependents"], annotations=READ_ONLY)
    def dependents(
        target: str,
        symbol: str | None = None,
        include_type_only: bool = True,
        follow_barrels: bool = False,
        limit: int = DEFAULT_LIMIT,
    ) -> CallToolResult:
        return ask(
            queries.dependents,
            target,
            symbol=symbol,
            include_type_only=include_type_only,
            follow_barrels=follow_barrels,
            limit=limit,
        )

    @server.tool(description=DESCRIPTIONS["impact"], annotations=READ_ONLY)
    def impact(
        target: str,
        max_depth: int | None = None,
        include_type_only: bool = True,
        follow_barrels: bool = False,
        limit: int = DEFAULT_LIMIT,
    ) -> CallToolResult:
        return ask(
            queries.impact,
            target,
            max_depth=max_depth,
            include_type_only=include_type_only,
            follow_barrels=follow_barrels,
            limit=limit,
        )

    @server.tool(description=DESCRIPTIONS["neighbors"], annotations=READ_ONLY)
    def neighbors(target: str, include_type_only: bool = True, limit: int = DEFAULT_LIMIT) -> CallToolResult:
        return ask(queries.neighbors, target, include_type_only=include_type_only, limit=limit)

    @server.tool(description=DESCRIPTIONS["cycles"], annotations=READ_ONLY)
    def cycles(include_type_only: bool = True, limit: int = DEFAULT_LIMIT) -> CallToolResult:
        return ask(queries.cycles, include_type_only=include_type_only, limit=limit)

    @server.tool(description=DESCRIPTIONS["key_files"], annotations=READ_ONLY)
    def key_files(include_type_only: bool = True, limit: int = 10) -> CallToolResult:
        return ask(queries.key_files, include_type_only=include_type_only, limit=limit)

    return server
