# Implementation Plan: MCP Server

**Branch**: `006-mcp-server` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-mcp-server/spec.md`

## Summary

This slice gives external coding agents the 004 graph queries over MCP. `graphora mcp` starts a server over
standard input/output, bound to one snapshot: a graph file, or one stored analysis from 005.

What it adds:

- **Graph query layer** (`graph/queries.py`, `graph/results.py`): two new questions, `definitions` (find a
  symbol by exact name, R8) and `overview` (what the graph covers, R9), also available as
  `graphora query … definitions|overview`.
- **MCP module** (`graphora/mcp/`): loading the served snapshot once (R2, R10) and nine read-only tools that
  only call the query layer and the store (R3). Results carry the 004 answer as structured data and
  `render_text` as text (R4). Limits (R5), tool errors (R6) and data/instruction separation (R7).
- **CLI**: `graphora mcp --graph FILE | --repository R --snapshot S [--database URL]` (R12).

What it does not change: the graph schema (v3), the store schema, the HTTP API, existing fixtures.

## Technical Context

**Language/Version**: Python ≥ 3.12 (unchanged)

**Primary Dependencies**: adds `mcp==2.3.0` (R1). No new dev dependencies (`anyio` comes with `mcp`)

**Storage**: none new. Store mode reads the 005 PostgreSQL store through `graphora.store.Store`

**Testing**: pytest. In-process MCP client; golden equivalence with `graphora query` over every fixture's
`queries.json`; unit tests for the new queries on synthetic documents; one stdio subprocess test; store
tests marked `db`; a performance test marked `slow` (R13)

**Target Platform**: developer laptop (macOS, Linux) as a child process of a coding agent; CI offline

**Project Type**: library module + CLI subcommand in the existing backend

**Performance Goals**: SC-003 — ready in < 3 s on a 5,000-file graph, each tool call < 1 s

**Constraints**: read-only; stdout = protocol only; deterministic results; bounded results (50/500 items,
200/400 lines); no repository files read from disk

**Scale/Scope**: one snapshot per process, one client per process

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Never execute analyzed code | Pass | the server reads a graph and stored text only; every tool is read-only and annotated so; no analysis from MCP |
| II. Deterministic output | Pass | results are 004 answers and their canonical JSON; equivalence and repeat tests |
| III. Provenance on every edge | Pass | answers keep every cited edge with full provenance (FR-010) |
| IV. Honest confidence | Pass | "likely" marks and the completeness note come from the query layer; instructions explain them |
| V. Facts by code | Pass | no model is involved; the server computes nothing itself |
| VI. Analyzed content is data | Pass | fixed descriptions and instructions; `read_lines` labeled as data; bounded results (R5, R7) |
| VII. One graph query layer | Pass | `definitions` and `overview` are added to `graph/`; MCP only calls it; schema unchanged |
| VIII. Golden tests | Pass | MCP answers compared with `graphora query` over the hand-written `queries.json`; definitions checked against `expected.json` |

Post-design re-check: still passes. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/006-mcp-server/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── mcp-tools.md
│   └── cli.md
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml                         # + mcp==2.3.0
├── src/graphora/
│   ├── graph/
│   │   ├── queries.py                     # + definitions(), overview()
│   │   └── results.py                     # + DefinitionMatch, Overview, Answer.definitions
│   ├── mcp/                               # new
│   │   ├── __init__.py                    # create_server(served) -> MCPServer
│   │   ├── served.py                      # Served, from_graph_file, from_store, PairNotFound
│   │   └── server.py                      # tool functions, descriptions, instructions, limits
│   └── cli/__init__.py                    # + `mcp` subcommand; + definitions/overview in `query`
└── tests/
    ├── mcp_client.py                      # helper: call_tool / list_tools through Client(server) with anyio.run
    ├── unit/test_definitions.py
    ├── unit/test_overview.py
    ├── unit/test_mcp_tools.py             # listing, annotations, limits, errors, data separation
    ├── golden/test_mcp_queries.py         # SC-001, SC-006
    ├── integration/test_mcp_cli.py        # exit codes, stdio subprocess
    ├── integration/test_mcp_store.py      # marked db
    └── integration/test_mcp_performance.py   # marked slow
```

**Structure Decision**: a new `graphora/mcp/` package, named in CLAUDE.md's target layout. Query additions go
to `graph/` (constitution VII). `store/` is reused as it is.

## Coordination

- `cli/__init__.py` and `pyproject.toml` are shared: the PR asks Ulyana to review. 007 (end-to-end pipeline,
  hers) may also touch the CLI: rebase on `main` before asking for review.
- `store/` is Ulyana's; this slice only calls `Store.open`, `get_analysis`, `has_repository` and `get_file`.
- CLAUDE.md gets the `graphora mcp` commands in a separate shared-files PR after this one is merged (as 005
  did with #15).
- 008 (verifier and agent tools) will call the same query layer; `definitions` is likely useful to it too.

## Commits

One commit per phase of `tasks.md`, pushed after `make check` passes. With the spec/plan/tasks commit this
gives 6 commits.

## Complexity Tracking

No constitution violations.
