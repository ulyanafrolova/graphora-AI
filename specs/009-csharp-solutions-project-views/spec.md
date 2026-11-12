# Feature Specification: C# Analysis, Slice 3 — Solutions and Project-level Views

**Feature Branch**: `docs/constitution-csharp` (PR #22, issue #19)

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: "slice 3 of issue 19: .sln files and project-level views in graph queries, HTTP API and
MCP (no frontend exists yet)"

## Clarifications

### Session 2026-11-12

- Q: How do `.sln` / `.slnx` solution files appear in the graph? → A: As solution nodes, with one edge per listed
  project (provenance: the line in the solution file); a listed project that does not exist is `unresolved`.
- Q: Are project-level dependencies stored in the graph or computed when asked? → A: Computed at query time from the
  file-level edges; the graph stays file-level and each project link carries its file edges as evidence.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See which projects depend on which through their code (Priority: P1)

A developer asks "what does project `Web` depend on?" and gets the projects (and packages) that `Web`'s files
actually use, each backed by the file → file edges and lines that prove it, next to the project references declared
in `Web.csproj`. The same question works for dependents, impact and cycles at project level.

**Why this priority**: Architects reason about .NET code in projects, not files. Slices 1–2 made the facts exact at
file level; this story turns them into the view people use, without storing anything derived.

**Independent Test**: Run project-level queries on the C# fixtures and compare with hand-written `queries.json`
answers.

**Acceptance Scenarios**:

1. **Given** `Web` files that use types of `Core` and `Infra`, **When** a developer asks for `Web`'s dependencies at
   project level, **Then** the answer lists `Core` and `Infra`, each with the file edges (file, line) that link them,
   and the `nuget` packages `Web` uses.
2. **Given** `Web.csproj` references `Tools.csproj` but no `Web` file uses a `Tools` type, **When** the same
   question is asked, **Then** `Tools` is listed as a declared reference with no code use ("declared, unused").
3. **Given** projects whose files form a loop across projects (A's files use B's types and B's use A's), **When**
   cycles are asked at project level, **Then** the loop is reported with one example chain of file edges.
4. **Given** a project, **When** impact is asked at project level, **Then** every project that depends on it
   directly or transitively through code is listed, nearest first.
5. **Given** file-level edges that are `heuristic`, **When** they are the only evidence for a project link,
   **Then** the project link is shown as "likely".

---

### User Story 2 - Solutions group projects (Priority: P2)

A developer analyzes a repository with `App.sln` (or `App.slnx`). The graph shows a solution node listing its
projects, so a reader can answer "which solution builds this project?" and see projects that are in no solution.

**Why this priority**: Solutions are how .NET repositories are organized for people and tools; without them the
project list has no grouping. It depends only on reading the solution file.

**Independent Test**: Run on a fixture with a `.sln` and a `.slnx` and compare with `expected.json`.

**Acceptance Scenarios**:

1. **Given** `App.sln` listing `src/Core/Core.csproj` and `src/Web/Web.csproj` with backslash paths, **When**
   analyzed, **Then** there is a solution node `App.sln` with an edge to each project node, at the line where the
   project is listed.
2. **Given** a solution entry for a project file that does not exist, **When** analyzed, **Then** that edge is
   `unresolved` with reason `not_found`.
3. **Given** solution folders (virtual folders inside the `.sln`) and non-C# entries (`.vcxproj`, `.fsproj`,
   `.sqlproj`), **When** analyzed, **Then** folders create no nodes and non-C# projects are listed as `unresolved`
   with reason `not_csharp` (they are not analyzed).
4. **Given** an `.slnx` (XML) solution, **When** analyzed, **Then** the result is the same as for the equivalent
   `.sln`.
5. **Given** a malformed solution file, **When** analyzed, **Then** it is listed with a `parse_error` flag and a
   warning, and analysis continues.

---

### User Story 3 - The same views for agents (Priority: P3)

A coding agent connected over MCP asks for the projects of a repository and for project-level dependencies, and gets
the same answers as the CLI, with the same evidence.

**Why this priority**: The MCP server is the agent-facing interface; it must not lag behind the CLI.

**Independent Test**: The existing tool-equals-CLI golden test covers the new question and option on every
fixture with `queries.json` entries.

**Acceptance Scenarios**:

1. **Given** a stored or file graph, **When** an agent calls the projects tool, **Then** the answer equals the CLI
   `projects` answer byte for byte.
2. **Given** an agent calls `dependencies` with project level, **Then** the answer equals the CLI answer.

---

### Edge Cases

- **Files with no project** (project-less or `ambiguous_project`): grouped under a "no project" pseudo-entry in the
  `projects` answer; they never form project links.
- **Edges inside one project**: not project links.
- **A project link supported only by `using` fallback edges**: shown with the confidence of those edges.
- **Edges to `ext:dotnet:` targets**: not shown at project level (the base library is not a project); `nuget`
  packages are shown, from `package_reference` edges and from code (`package_prefix`) separately.
- **A project listed in two solutions**: one edge from each solution.
- **The same project listed twice in one solution**: one edge per line.
- **Solution paths outside the analyzed folder**: `unresolved: not_found`; the path is never read.
- **`$(…)` in a solution path**: `unresolved: msbuild_property`.
- **Python, TS/JS and mixed repositories**: project-level questions answer "no projects in this snapshot" (empty
  answer, not an error).
- **Project-level `cycles` where a loop exists only through `heuristic` edges**: reported as "likely".

## Requirements *(mandatory)*

### Functional Requirements

**Solutions**

- **FR-001**: `.sln` (text format) and `.slnx` (XML) files MUST be read as data, never executed or evaluated. Each
  becomes a solution node; files already listed in coverage as `not_code` stay so.
- **FR-002**: Each project entry MUST become one edge from the solution to the project node, with provenance (line,
  column, snippet hash of the entry). Paths are resolved against the solution's folder with `\` and `/` accepted.
- **FR-003**: Entries whose file does not exist or lies outside the analyzed folder MUST be `unresolved:
  not_found`; entries with `$(…)` `unresolved: msbuild_property`; entries for non-C# project types
  `unresolved: not_csharp`. Solution folders and solution items (loose files) create nothing.
- **FR-004**: A malformed solution file MUST get the `parse_error` coverage flag and a warning in the existing
  format; analysis continues.

**Project-level views (query layer, CLI, MCP)**

- **FR-005**: The query layer MUST offer a `projects` question listing every project node with: its path, its
  solutions, its file count, its declared project references, its packages, and the projects its code uses and is
  used by (counts); plus a "no project" entry for project-less files.
- **FR-006**: `dependencies`, `dependents`, `impact` and `cycles` MUST accept a project level option. At project
  level, two projects are linked when any file of one has a resolved or heuristic edge (`imports` or
  `type_reference`) to a file of the other; each link lists those file edges as evidence, sorted. Declared
  `project_reference` edges are shown alongside, marked declared-only when no code edge backs them.
- **FR-007**: A project link's confidence MUST be the strongest of its evidence edges; links with only `heuristic`
  evidence keep the existing "likely" mark.
- **FR-008**: Nothing derived MUST be written into the graph document; project-level answers are computed from the
  stored file-level edges, deterministically.
- **FR-009**: The CLI (`graphora query`) and the MCP server MUST expose the `projects` question and the level option
  with identical answers (constitution VII). The HTTP API keeps serving the whole graph, which now includes solution
  nodes; it gains no query endpoints in this slice.

**Schema, determinism, ground truth**

- **FR-010**: The graph format MUST move to schema version 6 for the solution node, the solution membership edge and
  the `not_csharp` reason; every consumer changes in the same PR.
- **FR-011**: Determinism rules of 001–008 MUST hold for solutions and for project-level answers (byte-identical,
  sorted).
- **FR-012**: Fixtures MUST cover: a `.sln` with backslash paths, a solution folder, a missing project, a non-C#
  project and a `$(…)` path; an equivalent `.slnx`; a project in two solutions; a project in no solution; project
  links through type references and through fallback `using` edges; a declared-but-unused project reference; a
  project-level cycle; project-less files. `queries.json` MUST hold hand-written project-level answers, which the
  MCP golden test also checks.

### Key Entities

- **Solution node**: a `.sln` or `.slnx` file; lists projects.
- **Solution membership edge**: one project entry in a solution file, with provenance.
- **Project link** (query-time only): two projects plus the file edges that connect them, and whether a declared
  project reference exists.
- **Projects answer**: per project, its solutions, size, declared references, packages and code-level neighbours.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On every C# fixture, 100% of hand-checked solution nodes and edges are reproduced, and every
  hand-written project-level answer matches.
- **SC-002**: Every project link in an answer cites at least one file edge with file and line that a reader can open.
- **SC-003**: A declared project reference with no code use is reported as such in 100% of fixture cases.
- **SC-004**: CLI and MCP give byte-identical answers for every project-level question in the fixtures.
- **SC-005**: Project-level answers on a repository with 1,000 C# files in 20 projects take under 2 seconds.
- **SC-006**: Graph documents of non-C# fixtures differ from schema v5 only in the version number.

## Assumptions

- Slices 1–2 (features 007, 008) are the base: project nodes, ownership, file-level `imports` and `type_reference`
  edges are reused unchanged.
- `.sln` "Project" entries with the C# project type GUID or a `.csproj` path count as C# projects; other known
  project types are `not_csharp`. Solution configurations and platforms are not read.
- No frontend exists yet; the schema and query answers are its future contract.
- Query endpoints in the HTTP API are a separate feature; the API only serves documents in this slice.
- Project-level views for Python packages or npm workspaces are out of scope.
