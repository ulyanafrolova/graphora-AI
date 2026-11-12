---

description: "Task list for 009-csharp-solutions-project-views (slice 3 of issue #19)"
---

# Tasks: C# Analysis, Slice 3 — Solutions and Project-level Views (Schema v6)

**Input**: Design documents from `specs/009-csharp-solutions-project-views/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/graph.schema.json, contracts/cli.md,
quickstart.md

**Tests**: Required (FR-012, constitution VIII). Each task ships its own tests: write them first, confirm they fail,
then implement.

**Commits**: one commit per task, pushed right after it, on `docs/constitution-csharp` (PR #22), only after
`uv run pytest -m "not slow and not db"` passes (checked with `set -o pipefail`).

**Organization**:

- US1 (P1): project-level views (`level=project` for dependencies, dependents, impact, cycles) in the query layer,
  CLI and MCP;
- US2 (P2): solutions (`.sln`, `.slnx`) as graph facts;
- US3 (P3): the `projects` question for people and agents.

No setup phase: no new dependency or data file. Schema v6 is foundational.

## Format: `[ID] [P?] [Story] Description`

Paths are relative to the repository root; run commands from `backend/`.

---

## Phase 1: Foundational (schema v6)

- [X] T001 Move the graph format to schema v6 (research R7, data-model.md):
  - copy `specs/009-csharp-solutions-project-views/contracts/graph.schema.json` to `schema/graph.schema.json`;
  - `backend/src/graphora/graph/model.py`: `SolutionNode(path)` with `id = f"solution:{path}"`; `EdgeType` adds
    `"solution_member"`; `UnresolvedReason` adds `"not_csharp"`; `Node` union adds `SolutionNode`;
  - `serialize.py`: `SCHEMA_VERSION = 6`, solution nodes as `{"id", "kind": "solution", "path"}`;
  - `load.py`: reads solution nodes; `solution_member` edges need a solution-node source and solution nodes may be the
    source of no other edge type;
  - `queries.py`: `_kind` maps `solution`; `resolve()` accepts a `.sln`/`.slnx` path; `overview` `nodes` gains
    `"solution"`; `results.py` text line for overview nodes includes solutions;
  - tests: v6 accept/reject samples (the 7 in plan.md) in `backend/tests/contract/test_schema.py`; version cases in
    `test_load.py`, `test_serialize.py`, `test_overview.py`, `backend/tests/integration/test_store.py`; a solution
    round trip in `test_load.py`.

**Checkpoint**: suite green on v6.

---

## Phase 2: User Story 1 - Which projects depend on which through code (Priority: P1) 🎯 MVP

**Goal**: project-level `dependencies`, `dependents`, `impact`, `cycles` from file-level evidence, in the query layer,
CLI and MCP.

**Independent Test**: `uv run pytest tests/unit/test_project_view.py tests/golden -k csharp-types`.

- [X] T002 [US1] Create `backend/src/graphora/graph/project_view.py` (research R4): `ProjectView` built lazily from a
  `GraphIndex` (cached on it): file → project map; project links from non-`unresolved` `imports`/`type_reference`
  edges between files of different projects ("evidence", sorted by `edge_sort_key`); `declared` edges from resolved or
  heuristic `project_reference` edges; package links from `package_reference` (declared) and file edges to
  `ext:nuget:` (evidence); a NetworkX digraph with nodes and links inserted in sorted order; link confidence "strongest
  evidence confidence; declared edge's confidence when there is no evidence"; `declared_only` when evidence is empty.
  Unit tests in new `backend/tests/unit/test_project_view.py` on synthetic documents: evidence aggregation, edges inside
  one project ignored, project-less files ignored, `ext:dotnet:` ignored, declared-only links, heuristic-only links,
  packages from both sources, determinism.
- [X] T003 [US1] Add `level` to `dependencies`, `dependents`, `impact` and `cycles` in
  `backend/src/graphora/graph/queries.py` (research R5): `level="file"` unchanged; `level="project"` resolves the
  target to a project (`project:` id, `.csproj` path, or a C# file → its project; otherwise `NodeNotFound` status
  `not_a_project`), answers from `ProjectView` (impact and cycles use code links only, declared-only links excluded),
  rejects `symbol`, `follow_barrels` and `include_type_only=False` with `ValueError`. In
  `backend/src/graphora/graph/results.py`: `Link.declared: tuple[Edge, ...] = ()` (serialized only when non-empty),
  `Item.declared_only: bool = False` (serialized only when true), text rendering
  `<project>  <first evidence file>:<line> → <target> (+N more)` and `(declared, not used by code)`. Tests in
  `test_project_view.py` and `backend/tests/unit/test_dependents.py`/`test_cycles.py` for each question and error.
- [X] T004 [US1] CLI `--level {file,project}` in `backend/src/graphora/cli/__init__.py` (contracts/cli.md): passed to
  the four questions; usage error (exit 2, existing format) with `--symbol`, `--follow-barrels` or `--no-type-only` at
  project level; `not_a_project` → exit 1 `… is not a project`. Tests in `backend/tests/integration/test_query_cli.py`.
- [X] T005 [US1] MCP `level` argument (`"file"` default, `"project"`) on `dependencies`, `dependents`, `impact`,
  `cycles` in `backend/src/graphora/mcp/server.py`, with a sentence in each description; `_flags` in
  `backend/tests/golden/test_mcp_queries.py` passes `--level`; unit test in `backend/tests/unit/test_mcp_tools.py`.
- [X] T006 [US1] Hand-write project-level entries in `fixtures/repos/csharp-types/queries.json`: `dependencies` of
  `hosts/Web/Web.csproj` and of `src/App/App.csproj` at project level (code links via type references and fallback,
  packages if any), `dependents` of `src/App/App.csproj`, `impact` of `src/App/App.csproj`; derive each answer from
  the fixture code first, then compare with the tool and investigate every difference. The query and MCP golden tests
  pick them up.

**Checkpoint**: US1 works on existing fixtures through CLI and MCP.

---

## Phase 3: User Story 2 - Solutions group projects (Priority: P2)

**Goal**: solution nodes and `solution_member` edges.

**Independent Test**: `uv run pytest tests/unit/test_sln.py tests/golden -k csharp-multiproject`.

- [X] T007 [P] [US2] Create `backend/src/graphora/adapters/msbuild/sln.py` (`sln-reader@0.1.0`, research R1, R2):
  `read_sln(data) -> SolutionFacts` (UTF-8 with BOM, header line within the first 3 lines, `Project("{TYPE}") =
  "Name", "Path", "{GUID}"` entries with type GUID, path, line, column, line text; solution folders by GUID
  `2150E333-8FDC-42A3-9474-1A3956D46DE8`) and `read_slnx(data)` (expat, DTD refused, `Project Path=` anywhere,
  `Folder`/`File` ignored); `has_error` for malformed input. Tests in new `backend/tests/unit/test_sln.py`: both
  formats, CRLF, BOM, nested folders, missing header, DOCTYPE, positions.
- [X] T008 [US2] Membership and build (depends on T001, T007; research R3): `resolve_solution_member(solution, entry,
  projects)` in `backend/src/graphora/resolve/csharp.py` (`$(` → `msbuild_property`; not `.csproj` →
  `not_csharp`; outside root or missing → `not_found`; else resolved `project:`), solution pass in
  `backend/src/graphora/graph/build.py` (solution nodes for every walked `.sln`/`.slnx`, `solution_member` edges with
  extractor `sln-reader@0.1.0`, `parse_error` flag and warning), `current_extractors()` adds `sln-reader`, CLI warning
  text `ignoring <path>: not a readable solution file`, `extractor_versions.json` entry. Tests in
  `backend/tests/unit/test_build_analyze.py` and `backend/tests/integration/test_cli.py`.
- [X] T009 [US2] Extend `fixtures/repos/csharp-multiproject/` (research R8): `Graphora.sln` (backslash paths, a
  solution folder, a missing project, an `.fsproj`, a `$(…)` path) and `Graphora.slnx` (same projects minus `Tools`),
  two new projects `src/LoopA`, `src/LoopB` whose files use each other's types (a project-level cycle); update
  `expected.json` by hand and add project-level `cycles` and `dependencies` of `src/Web/Web.csproj` (with
  `Tools` declared, not used) to `queries.json`.

---

## Phase 4: User Story 3 - The `projects` question (Priority: P3)

**Goal**: one answer summarising every project, for CLI and MCP.

**Independent Test**: `uv run pytest tests/unit/test_project_view.py -k projects tests/golden -k projects`.

- [ ] T010 [US3] `projects` question (research R6, data-model.md § Projects answer entry) in
  `backend/src/graphora/graph/queries.py`/`project_view.py`/`results.py`, CLI question `projects` and MCP tool
  `projects`; empty list for graphs without projects; hand-written `projects` entries in the `queries.json` of
  `csharp-multiproject`, `csharp-types` and `py-flat` (empty). Unit tests in `test_project_view.py`, MCP test in
  `test_mcp_tools.py`.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T011 [P] Extend `backend/tests/integration/test_safety_cs.py`: a `.slnx` with a `DOCTYPE` entity bomb and a `.sln`
  listing `..\..\outside\X.csproj`; no process, no read outside the root, `parse_error` / `not_found` as specified.
- [ ] T012 [P] Extend the C# test in `backend/tests/integration/test_performance.py`: after analysis, project-level
  `impact` of `P0` and `cycles` answer in under 2 s in total (SC-005).
- [ ] T013 Docs: `README.md` (status row for 009, schema v6 diagram: solution node, `solution_member`; quick start
  example of `--level project` and `projects`), `docs/product/project-context.md` § 7 (C# complete for issue #19);
  run every scenario of `specs/009-csharp-solutions-project-views/quickstart.md` and fix drift.

---

## Dependencies & Execution Order

- T001 → US1 (T002 → T003 → T004, T005 → T006) → US2 (T007 ∥ US1; T008 needs T001, T007; T009 needs T008 and T003)
  → US3 (T010 needs T003 and T008) → Polish (T011 ∥ T012 → T013).

### Parallel opportunities

- T007 alongside US1; T004 with T005 once T003 is done; T011 with T012.

```text
Task: "T004 [US1] CLI --level in backend/src/graphora/cli/__init__.py"
Task: "T005 [US1] MCP level argument in backend/src/graphora/mcp/server.py"
Task: "T007 [US2] solution readers in backend/src/graphora/adapters/msbuild/sln.py"
```

## Implementation Strategy

1. MVP: T001–T006 — project-level questions over the existing graphs.
2. US2 adds solutions; US3 adds the summary question.
3. Then issue #19 is complete; PR #22 goes to review.
