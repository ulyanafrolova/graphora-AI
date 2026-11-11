# Feature Specification: MCP Server

**Feature Branch**: `006-mcp-server`

**Created**: 2026-11-11

**Status**: Draft

**Input**: User description: "MCP" — feature 006 from the team plan (`docs/product/team-workflow.md`,
round 3): an MCP server that gives external coding agents (Claude Code, Cursor and others) the same graph
queries that people use, over one analyzed snapshot.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A coding agent asks the graph instead of guessing (Priority: P1)

A developer has a graph of a repository (a graph file written by `graphora analyze`). They connect Graphora
to their coding agent with one command, for example
`claude mcp add graphora -- graphora mcp --graph graph.json`. When they ask the agent "what breaks if I
change `auth/service.py`?", the agent calls Graphora's impact tool and answers from the computed list, citing
the `file:line` of every import in the chain, instead of searching the code with text search.

**Why this priority**: This is the product promise "Graphora gives agents a map through MCP" and the base of
the benchmark (feature 013: the same model with text search versus with Graphora MCP). Every later MCP use
needs these tools.

**Independent Test**: Start the server on a fixture graph, connect a test MCP client, list the tools and call
each graph query tool. Every answer must equal the answer of the same question from `graphora query` on the
same graph.

**Acceptance Scenarios**:

1. **Given** the server is started on a graph file, **When** a client lists the tools, **Then** it gets the
   graph tools (dependencies, dependents, impact, neighbors, cycles, key files, graph overview), each with a
   description and typed parameters, and each marked as read-only.
2. **Given** a graph where `api/routes.py` imports `auth/service.py` on line 3, **When** the client calls the
   dependents tool for `auth/service.py`, **Then** the result lists `api/routes.py` with the edge at line 3,
   its confidence and the snapshot id, exactly as `graphora query … dependents auth/service.py` reports it.
3. **Given** the same server, **When** the client calls the impact tool with a maximum distance of 2,
   **Then** the result holds only dependents at distance 1 and 2 and says that the search was cut.
4. **Given** a target path that is not in the graph, **When** any tool is called with it, **Then** the client
   gets a tool error that says why (for example "not analyzed: detected only" or "not in snapshot"), and the
   server keeps running.
5. **Given** the same tool call made twice, **When** the results are compared, **Then** they are identical.
6. **Given** the client calls the overview tool, **Then** it gets the snapshot id, the languages and the counts
   of analyzed, detected-only and skipped files, and the number of unresolved imports, so the agent knows what
   the graph does and does not cover.

---

### User Story 2 - Find where a symbol is defined (Priority: P2)

The agent is asked about a class or function by name ("what depends on `AuthService`?"). It first calls the
definitions tool with the name, gets the file and line where `AuthService` is defined, and then calls the
dependents or impact tool on that file with the symbol filter.

**Why this priority**: Agents and people ask about symbols, not file paths. Without a lookup the agent falls
back to text search, which is what the benchmark wants to avoid. Graph queries alone (US1) still work when
the agent already knows the file, so this comes second.

**Independent Test**: On the fixture graphs, call the definitions tool with known class and function names
and compare with the definitions written in each fixture's `expected.json`.

**Acceptance Scenarios**:

1. **Given** `auth/service.py` defines `class AuthService` on line 12, **When** the client asks for
   definitions named `AuthService`, **Then** it gets `auth/service.py`, line 12, kind `class`.
2. **Given** two files define a function `load`, **When** the client asks for `load`, **Then** both are
   returned in path order.
3. **Given** a method `Logger.write`, **When** the client asks for `write`, **Then** the method is found by its
   short name and returned with its full name `Logger.write`.
4. **Given** a TS file exports `Button` under the name `default`, **When** the client asks for `Button`,
   **Then** the result shows the definition and the names it is exported under.
5. **Given** a name that no file defines, **When** the client asks for it, **Then** the result is an empty
   list, not an error, together with the note on not-analyzed files.

---

### User Story 3 - Work with stored snapshots and read cited lines (Priority: P3)

The team keeps analyses in the store (feature 005). A developer starts the server for one stored repository
and snapshot instead of a graph file. In addition to the graph tools, the agent can read the exact lines of a
file as they were in that snapshot, so it can check a citation like `api/routes.py:3` even when the
developer's working copy has changed since the analysis.

**Why this priority**: Commit-pinned evidence is a core claim of the product, and the store already holds
the file text. But a developer with a local checkout and a graph file (US1) can work without a database, so
this is an addition.

**Independent Test**: Store a fixture analysis, start the server for that repository and snapshot, call the
graph tools and the read-lines tool, and compare with the HTTP API of feature 005 for the same pair.

**Acceptance Scenarios**:

1. **Given** a stored analysis of repository `github.com/o/r` at snapshot `S`, **When** the server is started
   for that pair, **Then** every graph tool answers on that snapshot and the overview names the repository.
2. **Given** the same server, **When** the client asks for lines 1–5 of `api/routes.py`, **Then** it gets those
   lines with their numbers, marked as file content (data, not instructions), and the snapshot id.
3. **Given** a path that is skipped, binary, outside the snapshot or written with `..`, **When** lines are
   asked for, **Then** the client gets a tool error and no data from outside the stored snapshot.
4. **Given** a request for 5,000 lines, **When** the call is made, **Then** at most the line limit is returned,
   and the result says it was cut and how to ask for the rest.
5. **Given** the pair is not in the store or the database cannot be reached, **When** the server is started,
   **Then** it stops before serving with a clear message and a distinct exit code.

---

### Edge Cases

- A tool is called with a missing or wrongly typed argument: a tool error names the argument; the server keeps
  running. Unknown extra arguments are ignored (behaviour of the MCP SDK).
- A tool result would be very large (thousands of dependents): every list tool has a default limit and a
  maximum; the result holds the total count and a "truncated" flag so the agent can ask again with a larger
  limit or a narrower question.
- The graph file is invalid, has an unsupported schema version or does not exist: the server does not start
  and says why.
- File names, symbol names, import references and file lines can contain text that looks like instructions
  ("ignore previous instructions…"): they are returned as data fields, never as part of a tool description,
  and file lines are labeled as file content.
- The server never writes anything on the standard output except protocol messages; logs and errors go to
  the standard error.
- Two clients cannot share one server process over standard input/output; each client starts its own.
- A graph with heuristic edges: results keep the "likely" marking from the query layer.

## Requirements *(mandatory)*

### Functional Requirements

**Starting the server**

- **FR-001**: The CLI MUST start an MCP server that speaks the protocol over standard input and output, bound
  to exactly one snapshot for its whole life: either a graph file (`--graph <file>`, or `-` is not allowed
  because standard input is the protocol channel) or one stored (repository, snapshot) pair.
- **FR-002**: The graph MUST be loaded and validated once at start. An invalid or missing graph, an unknown
  stored pair or an unreachable store MUST stop the server before it serves, with a message on the standard
  error and a non-zero exit code distinct per cause.
- **FR-003**: The server MUST report its name, its version and a short description of what it offers and of
  the snapshot it serves.

**Tools**

- **FR-004**: The server MUST offer one tool per graph question of feature 004: dependencies, dependents (with
  the symbol filter), impact (with the maximum distance), neighbors, cycles and key files, with the same
  options (type-only links, barrel following, limit).
- **FR-005**: The server MUST offer an overview tool: snapshot id, repository name when known, schema
  version, extractor versions, languages, counts of analyzed, detected-only, not-code and skipped files,
  number of nodes, edges and unresolved imports.
- **FR-006**: The server MUST offer a definitions tool: given a name, return every definition whose name or
  last name part (after the final `.`) equals it, with file, line, kind, full name and, for TS/JS, the names
  it is exported under. Matching is exact and case-sensitive.
- **FR-007**: In store mode only, the server MUST offer a read-lines tool: given a path and a line range,
  return the numbered lines of that file as stored for the snapshot, or a tool error when the file has no
  text or the path is not a stored file.
- **FR-008**: Every tool MUST be declared read-only and MUST NOT write files, start an analysis, download
  anything or change the store.
- **FR-009**: Each tool MUST have a description that says what it answers, which arguments it takes and what
  the confidence levels mean, written so a small model can choose the right tool.

**Results**

- **FR-010**: Graph tool results MUST be the answers of the feature 004 query layer, unchanged: same items,
  order, edges with full provenance, confidence, type-only marks, completeness note, snapshot id and echoed
  options. The server MUST NOT compute any graph fact itself.
- **FR-011**: Each result MUST be available both as structured data (the answer document of feature 004) and
  as readable text with `file:line` chains for models that read only text.
- **FR-012**: Every list result MUST be bounded: a default limit and a maximum limit per tool, the total count
  and a truncated flag. Read-lines results MUST be bounded by a maximum number of lines per call.
- **FR-013**: The same tool call on the same snapshot MUST give an identical result.
- **FR-014**: Errors in a call (unknown target, bad argument, file without text) MUST be returned as tool
  errors with a message that says what to change; they MUST NOT stop the server.

**Safety**

- **FR-015**: Text that comes from the analyzed repository (paths, names, references, file lines) MUST appear
  only in result data, never in tool names, descriptions or server instructions. Read-lines results MUST
  label their content as file content of the snapshot.
- **FR-016**: The server MUST NOT read the analyzed repository's files from disk; file text comes only from
  the store.
- **FR-017**: All graph logic MUST stay in the graph query layer. The definitions lookup and the overview are
  added there as new queries (and to `graphora query`), and the MCP server only calls them.

### Key Entities

- **Served snapshot**: the one graph (and, in store mode, its stored files) the server answers about; has a
  snapshot id and, in store mode, a repository name.
- **Tool**: a named, read-only operation with typed arguments, a description, and a result.
- **Tool result**: structured answer plus readable text; or a tool error with a message.
- **Definition match**: file, line, kind, full name, exported names.
- **Line range result**: path, snapshot id, first and last line, total lines, the numbered lines, a cut flag.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every fixture graph and every question in its hand-written `queries.json`, the MCP tool
  result equals the `graphora query --format json` answer byte for byte.
- **SC-002**: A developer connects the server to Claude Code with one command from the quickstart and gets a
  correct impact answer for a fixture file on the first try.
- **SC-003**: On a graph at the default ingest limits (5,000 files) the server is ready in under 3 seconds,
  and each tool call answers in under 1 second.
- **SC-004**: 0 tool calls in the test suite write to disk, open a network connection other than the store,
  or change stored data; 0 tool descriptions contain text from an analyzed repository.
- **SC-005**: No tool result in the test suite is larger than its documented bound (items or lines).
- **SC-006**: 100% of definitions written in the fixtures' `expected.json` are found by name.

## Assumptions

- This is feature 006 from the team plan, owned by Anna. It builds on 004 (queries, `graph/queries.py`) and
  005 (store, `store/`). Feature 007 (end-to-end pipeline) and 008 (verifier, agent tools) will reuse the same
  query layer; the agents of 009 do not use this server.
- Only the standard input/output transport is offered; the server runs on the developer's machine as a child
  of the agent. A network transport and authentication are out of scope.
- The server serves one snapshot per process. To ask about another snapshot, the developer starts another
  server. Switching snapshots inside a session is out of scope.
- In graph-file mode there is no read-lines tool: the agent reads files from its own checkout. The overview
  tells the agent which snapshot the graph is pinned to so it can notice a mismatch.
- Analysis from inside MCP (giving a URL to analyze) is out of scope: it downloads and writes, and tools are
  read-only.
- The symbol-scoped impact question from 004 (start the impact search only from importers of one symbol)
  stays as it is in 004: dependents has the symbol filter; impact does not.
- Default limits: 50 items per list (maximum 500), 200 lines per read (maximum 400). They keep answers within
  what a local 8B model can read.
