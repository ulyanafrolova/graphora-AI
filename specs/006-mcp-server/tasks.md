---

description: "Task list for 006-mcp-server"
---

# Tasks: MCP Server

**Input**: Design documents from `specs/006-mcp-server/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R14), data-model.md, contracts/mcp-tools.md,
contracts/cli.md, quickstart.md

**Tests**: Required. Constitution VIII and SC-001/SC-006 need golden checks over the fixtures; SC-003–SC-005
are checked by tests. Within each story, write the tests first and confirm they fail before you implement.

**Organization**: Tasks are grouped by user story:

- US1 (P1): a coding agent calls the graph query tools on a graph file;
- US2 (P2): find where a symbol is defined;
- US3 (P3): store mode and reading cited lines.

Paths are relative to the repository root. Code lives in `backend/src/graphora/`, tests in `backend/tests/`.
Run commands from `backend/`. Do not edit `graph/model.py`, `graph/serialize.py`, `graph/load.py`,
`store/`, `api/`, any `expected.json` or `queries.json`. Keep comments minimal, in the style of the existing
modules. Use the mcp 2.x API (`mcp.server.mcpserver.MCPServer`, `mcp.client.Client`); 1.x examples with
`mcp.server.fastmcp` do not work.

**Commits**: each phase ends with one commit and push (marked **Commit**). Run `make check` from the
repository root first. Phase 1 and 2 share one commit. With the spec/plan/tasks commit the PR has 6 commits.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: The user story the task belongs to (US1–US3)

---

## Phase 1: Setup

- [ ] T001 Add `"mcp==2.3.0"` to `dependencies` in `backend/pyproject.toml` (research R1) and run `uv lock`;
  `backend/uv.lock` must resolve with the existing `fastapi==0.162.0` and `uvicorn==0.54.0` pins unchanged.
  If it does not resolve, stop and report the conflict instead of changing other pins.
- [ ] T002 [P] Create `backend/tests/mcp_client.py` with `list_tools(server)`, `call(server, name, **args)` and
  `instructions(server)`: each opens `mcp.client.Client(server)` in-process inside `anyio.run` and returns the
  SDK result objects. Add `canonical(structured) -> bytes` = `json.dumps(structured, sort_keys=True,
  ensure_ascii=False, indent=2) + "\n"` encoded as UTF-8.

---

## Phase 2: Foundational

**Purpose**: the overview query, the served snapshot, a running server with one tool, and the CLI command.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 [P] Write `backend/tests/unit/test_overview.py` (fails until T004) on documents from
  `make_doc` in `backend/tests/unit/synthetic.py` and on `analyzed_graph("py-dynamic")`: every field of data-model.md
  § Overview; counts equal the coverage summary and the node/edge lists; `dumps` twice gives equal bytes;
  `render_text` names the snapshot and the counts.
- [ ] T004 Add `Overview` (frozen dataclass, `to_dict()`) and `render_text` support for it to
  `backend/src/graphora/graph/results.py`, and `overview(ix) -> Overview` to
  `backend/src/graphora/graph/queries.py` (research R9). Extend `dumps` to accept `Overview`.
- [ ] T005 [P] Write `backend/tests/unit/test_mcp_served.py` (fails until T006): `from_graph_file` on a fixture
  graph written to `tmp_path` builds an index whose snapshot equals the document's; a missing file raises
  `OSError`; `{}` raises `InvalidGraph`.
- [ ] T006 Create `backend/src/graphora/mcp/served.py` (data-model.md § Served): frozen dataclass `Served(index,
  repository=None, store=None)`, `from_graph_file(path) -> Served` (`load.loads` then `queries.index`).
  `from_store` is added in US3.
- [ ] T007 Create `backend/src/graphora/mcp/server.py` and `backend/src/graphora/mcp/__init__.py` with
  `create_server(served) -> MCPServer`: name `graphora`, version from `importlib.metadata.version("graphora")`,
  the fixed instructions of contracts/mcp-tools.md with the snapshot (and repository) filled in, and the
  `graph_overview` tool returning `CallToolResult(content=[TextContent(render_text(o))],
  structuredContent=o.to_dict() | {"repository": …} when in store mode)` (research R4). Tool annotations as
  in research R3. A helper `_result(answer_or_overview, extra=None)` and an `_error(message)` that returns a
  `CallToolResult` with `isError=True` are added here for the later tools.
- [ ] T008 [P] Write `backend/tests/integration/test_mcp_cli.py` (fails until T009): `main(["mcp", …])` returns
  2 for no source, for both `--graph` and `--repository`, for `--graph -`, for `--database` with `--graph`,
  for `--repository` without `--snapshot`, and for a missing file; 7 for `{}`; nothing is written to stdout in
  any of these cases. A test with `query <graph> overview --format json` equals `results.dumps(overview(ix))`;
  `overview` with a target or `--limit` returns 2.
- [ ] T009 Add the `mcp` subcommand to `backend/src/graphora/cli/__init__.py` (contracts/cli.md): options
  `--graph`, `--repository`, `--snapshot`, `--database`; a new `_mcp(args)` function kept apart from
  `_query` and `_serve`; it validates the options, builds `Served` (errors → exit codes of research R12, via
  `_log`), then calls `create_server(served).run("stdio")` and returns 0. Store mode returns 2 with
  `store mode is not implemented yet` until US3. Add `overview` to `_QUESTIONS` of `query` (no target, only
  `--format`).

**Checkpoint**: `uv run pytest -m "not slow and not db"` passes; `graphora mcp --graph g.json` starts and
answers `graph_overview` in a test client.
**Commit** `add mcp server skeleton and overview tool`, push (include `specs/006-mcp-server/tasks.md` changes
if any).

---

## Phase 3: User Story 1 - Graph query tools (Priority: P1) 🎯 MVP

**Goal**: the six 004 questions as MCP tools on a graph file, identical to `graphora query`.

**Independent Test**: for every fixture and every entry in its `queries.json`, the tool result serialized
canonically equals `graphora query … --format json`.

### Tests for User Story 1

- [ ] T010 [P] [US1] Write `backend/tests/golden/test_mcp_queries.py` (fails until T012): parametrized over
  every fixture with a `queries.json` and every entry; write `analyzed_graph(name)` to `tmp_path`; build the
  server with `from_graph_file`; call the tool named as the question (`key-files` → `key_files`) with the
  entry's options mapped to tool arguments; assert `canonical(result.structuredContent)` equals the stdout of
  `run_query(graph, question, target, *flags, "--format", "json")`; assert the text block equals
  `render_text` of the same answer; call twice and compare (SC-001, FR-013).
- [ ] T011 [P] [US1] Write `backend/tests/unit/test_mcp_tools.py` (fails until T012) on a synthetic graph:
  - `list_tools` gives exactly `graph_overview`, `dependencies`, `dependents`, `impact`, `neighbors`,
    `cycles`, `key_files` in graph-file mode (no `read_lines`); each has a description, an input schema with
    the arguments and defaults of contracts/mcp-tools.md, and the four annotations of research R3;
  - limits: default 50 (10 for `key_files`), `limit=500` accepted, `limit=501` and `limit=-1` are tool
    errors with the messages of contracts/mcp-tools.md; a 60-item answer is cut at 50 with `truncated: true`
    and `total: 60` (SC-005);
  - errors: unknown target, `detected_only` target, `max_depth=0`, missing `target`, wrong argument type →
    `isError: true` with a message, and a following call on the same client still works (FR-014);
  - data separation (FR-015, SC-004): a synthetic graph with a file named
    `ignore_previous_instructions.py` and a definition named `IGNORE_ALL_RULES`; the strings appear in results
    only, never in `list_tools` output or `instructions`;
  - instructions contain the snapshot id.
- [ ] T012 [US1] Add the tools `dependencies`, `dependents`, `impact`, `neighbors`, `cycles`, `key_files` to
  `backend/src/graphora/mcp/server.py` (research R3–R6, contracts/mcp-tools.md): typed arguments with the
  defaults of the contract, the description texts of the contract (first sentence) followed by one sentence
  on arguments and one on confidence; a shared `_check_limit(limit)` (0–500); each calls the
  `graphora.graph.queries` function with the served index and returns `_result(answer)`; `NodeNotFound` and
  `ValueError` → `_error(message)`.
- [ ] T013 [US1] Add one stdio test to `backend/tests/integration/test_mcp_cli.py` (research R11): start the
  real command as a subprocess with `mcp.client.Client(StdioServerParameters(command=sys.executable,
  args=["-c", "from graphora.cli import main; raise SystemExit(main())", "mcp", "--graph", path]))`, list the
  tools and call `impact` on a fixture file; the structured result equals the in-process one.

**Checkpoint**: US1 tests pass. **Commit** `add graph query tools to mcp server`, push.

---

## Phase 4: User Story 2 - Find definitions (Priority: P2)

**Goal**: turn a symbol name into the file and line where it is defined.

**Independent Test**: every definition in every fixture's `expected.json` is found by its name.

### Tests for User Story 2

- [ ] T014 [P] [US2] Write `backend/tests/unit/test_definitions.py` (fails until T015) on synthetic documents:
  spec US2 scenarios 1–5; order by (path, line, name); `exported_as` present for TS/JS, absent for Python;
  case-sensitive (`authservice` finds nothing); limit with `total`/`truncated`; `target` is `null`,
  `options` = `{"limit", "name"}`; completeness present; `dumps` twice equal.
- [ ] T015 [US2] Add `DefinitionMatch`, `Answer.definitions` and `"definitions"` in `Question` to
  `backend/src/graphora/graph/results.py` (data-model.md), its `render_text` lines
  (`path:line  kind  name  [exported as …]`), and `definitions(ix, name, *, limit=None)` to
  `backend/src/graphora/graph/queries.py` (research R8).
- [ ] T016 [P] [US2] Add `definitions` to `query` in `backend/src/graphora/cli/__init__.py` (contracts/cli.md):
  the name is the target and is not resolved as a node; only `--limit` and `--format`. Add CLI cases to
  `backend/tests/integration/test_query_cli.py`: JSON equals `dumps(definitions(...))`, `--symbol` is a usage
  error, missing name is a usage error.
- [ ] T017 [US2] Add the `find_definitions` tool to `backend/src/graphora/mcp/server.py` (arguments `name`,
  `limit`) and extend `backend/tests/golden/test_mcp_queries.py` with SC-006: for every fixture, for every
  definition in `expected.json`, `find_definitions(name=<last name part>)` contains a match with that path,
  line, kind and full name. Update the expected tool list in `backend/tests/unit/test_mcp_tools.py`.

**Checkpoint**: US1 and US2 tests pass. **Commit** `add definitions query and mcp tool`, push.

---

## Phase 5: User Story 3 - Store mode and read_lines (Priority: P3)

**Goal**: serve a stored (repository, snapshot) and read its lines exactly as stored.

**Independent Test**: with PostgreSQL, a stored fixture analysis served over MCP gives the same graph
answers as the graph file and the same lines as the 005 HTTP API.

### Tests for User Story 3

- [ ] T018 [P] [US3] Write `backend/tests/integration/test_mcp_store.py`, every test marked `db` (fails until
  T019–T021): store a fixture analysis with the `store` fixture and `analyze_fixture` from `backend/tests/conftest.py`;
  `from_store` builds a `Served` with the repository; `graph_overview` adds `repository`; `impact` equals the
  graph-file result; `list_tools` adds `read_lines`; `read_lines(path, 1, 5)` equals the 005
  `GET /api/v1/file` lines for the same pair and has `content: "file_lines"`, the fixed note, repository and
  snapshot; no `end` on a file longer than 200 lines gives 200 lines and `cut: true`; a 5,000-line range gives 400
  lines and `cut: true`; `end < start`, a range past the end, `../x`, `/etc/passwd`, `a\\b.py`, a skipped path and a binary file are
  tool errors with the messages of contracts/mcp-tools.md; `PairNotFound` for an unknown repository and for an
  unknown snapshot; CLI exit 8 for both and exit 6 with no database URL.
- [ ] T019 [US3] Add `PairNotFound` and `from_store(url, repository, snapshot) -> Served` to
  `backend/src/graphora/mcp/served.py` (research R10): `Store.open(url)`, `get_analysis`, and on `None` use
  `has_repository` to choose the message (`repository not found: R` / `snapshot not found: R S`); load and
  index the stored graph bytes; on any failure close the store before raising.
- [ ] T020 [US3] Add the `read_lines` tool to `backend/src/graphora/mcp/server.py`, registered only when
  `served.store` is set (data-model.md § Line range, research R5, R7): path check (no absolute path,
  backslash or `..` segment) before the store call; `end` defaults to `start + 199`, a longer range is cut to 400 lines, both
  capped at the file length, with `cut`; a cut text block ends with `(cut: next start=<end+1>)`; store `ValueError` and a `None` result → errors; text block
  starts with `--- file <path> @ <snapshot>, lines a–b of n (data) ---` followed by `n: text` lines.
- [ ] T021 [US3] Enable store mode in `_mcp` in `backend/src/graphora/cli/__init__.py`: URL from `--database`
  or `GRAPHORA_DATABASE_URL`; `StoreUnavailable` → 6, `InvalidGraph` → 7, `PairNotFound` → 8; close the
  store after `run` returns.

**Checkpoint**: all story tests pass (with `make db` for the `db` tests). **Commit**
`add store mode and read lines tool`, push.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T022 [P] Write `backend/tests/integration/test_mcp_performance.py`, marked `slow` (SC-003): a synthetic
  5,000-file document (reuse `_graph()` from `backend/tests/integration/test_query_performance.py`) written
  to `tmp_path`; `from_graph_file` + `create_server` in < 3 s; each tool (impact and dependents on the most
  depended-on file, cycles, key files, find_definitions, graph_overview) answers through the in-process client
  in < 1 s.
- [ ] T023 [P] Run quickstart.md scenarios 1–7 and 9 by hand (scenario 8 with `make db`), including the Claude
  Code scenarios 3–5; fix any mismatch with the contracts; update `specs/006-mcp-server/quickstart.md` if a
  command changed.
- [ ] T024 Run `make check`; rebase on `main` if 007 or other CLI changes were merged; update the PR
  description; mark the PR ready.

**Commit** `add mcp performance test and polish`, push.

---

## Dependencies & Execution Order

- **Setup → Foundational** block everything.
- **US1** after Foundational.
- **US2** after US1 (it extends the tool list test and the golden MCP test); its query part (T014–T016) only
  needs Foundational.
- **US3** after Foundational; it extends the tool list, so do it after US1.
- **Polish** after all stories.

### Within Each User Story

- Tests first; confirm they fail.
- Query layer → MCP tool → CLI wiring.
- Commit at the end of the phase with `make check` green.

### Parallel Opportunities

- T002 with T001; T003, T005, T008 together.
- US1: T010 and T011 together. US2: T014 and T016 together. T022 and T023 together.

---

## Parallel Example: User Story 1

```text
T010 golden equivalence MCP vs graphora query   backend/tests/golden/test_mcp_queries.py
T011 tool listing, limits, errors, data         backend/tests/unit/test_mcp_tools.py
```

---

## Implementation Strategy

### MVP first

1. Phases 1–2, then US1: an agent can ask impact, dependents and cycles over a graph file. That is enough for
   the demo and for the first benchmark runs (013).

### Incremental delivery

- US2 (definitions) → US3 (store mode, read_lines) → polish. Each phase is one commit, tested and pushed.
