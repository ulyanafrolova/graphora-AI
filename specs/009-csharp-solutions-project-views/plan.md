# Implementation Plan: C# Analysis, Slice 3 — Solutions and Project-level Views (Schema v6)

**Branch**: `docs/constitution-csharp` (PR #22, issue #19) | **Date**: 2026-11-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-csharp-solutions-project-views/spec.md`

## Summary

Solutions become graph facts; project-level questions are answered from the file-level facts.

- **Solutions** (stored): `.sln` (line reader) and `.slnx` (XML, DTD refused) give solution nodes and one
  `solution_member` edge per project entry; missing, non-C# and `$(…)` entries are `unresolved` with a reason (R1–R3).
- **Project view** (computed): a lazily built project link graph per `GraphIndex`; each link carries its file-level
  evidence edges and any declared `project_reference` (R4). `dependencies`, `dependents`, `impact` and `cycles` take
  `level=project`; a new `projects` question summarises every project (R5, R6).
- **Interfaces**: CLI `--level` and `projects`; MCP `level` argument and `projects` tool; HTTP API serves v6 (no new
  endpoints).

## Technical Context

**Language/Version**: Python ≥ 3.12 (unchanged)

**Primary Dependencies**: unchanged (NetworkX for the project link graph; standard-library expat for `.slnx`)

**Storage**: unchanged (store sees schema v6)

**Testing**: golden (solutions in `csharp-multiproject`, project-level `queries.json` in two fixtures, MCP
equivalence), contract (v6 samples), unit (sln/slnx readers, membership resolution, project view, `projects`),
integration (CLI options and errors, safety for solution files, performance)

**Target Platform**: macOS and Linux, no .NET SDK

**Project Type**: CLI, MCP server and HTTP API in `backend`

**Performance Goals**: project-level answers under 2 s on 1,000 files / 20 projects (SC-005)

**Constraints**: nothing derived stored; deterministic answers; solution files read as data only

**Scale/Scope**: solutions with tens to hundreds of entries

No open questions remain.

## Constitution Check

*GATE: checked before Phase 0 and after Phase 1.* Constitution 1.1.0.

| Principle | How this plan complies | Status |
|---|---|---|
| I. Never execute analyzed code | `.sln` read line by line, `.slnx` by expat with DTD refused; no `dotnet sln`, no MSBuild; paths only looked up among walked files | ✅ |
| II. Deterministic output | Sorted entries, nodes inserted into NetworkX in sorted order, evidence sorted by the edge key | ✅ |
| III. Provenance on every edge | `solution_member` edges carry the entry's line, column and snippet hash; every project link cites its file edges | ✅ |
| IV. Honest confidence | Missing/non-C#/`$(…)` entries `unresolved` with reasons; project links take the strongest evidence confidence; declared-only links are labelled, not upgraded | ✅ |
| V. Facts by code | Project views are computed by algorithms over stored facts; no model | ✅ |
| VI. Content is data | No model reads content | ✅ (n/a) |
| VII. One graph query layer | Project view lives in `graph/project_view.py`, called by `graph/queries.py`; CLI and MCP only call it. Schema v6 with all consumers in this PR | ✅ |
| VIII. Golden tests | Hand-written solution expectations and project-level answers | ✅ |
| Workflow | Same branch and PR; spec covers slice 3 only | ✅ |

**Re-check after Phase 1:** no violations. The draft v6 schema accepts the current output of five fixtures (version
6) and a sample with solution nodes, and rejects 7 invalid samples (membership from a project, to a file, with a
directive; `imports` from a solution; `not_csharp` on a heuristic edge; a non-`.sln` solution path; a v5 document).

## Project Structure

### Documentation (this feature)

```text
specs/009-csharp-solutions-project-views/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/{graph.schema.json, cli.md}
├── checklists/requirements.md
└── tasks.md               # /speckit-tasks
```

### Source Code (repository root)

```text
schema/graph.schema.json                  # v5 → v6
backend/src/graphora/
├── adapters/msbuild/sln.py               # new: .sln and .slnx readers (sln-reader@0.1.0)
├── resolve/csharp.py                     # + solution membership resolution
├── graph/
│   ├── model.py, serialize.py, load.py   # SolutionNode, solution_member, not_csharp, SCHEMA_VERSION = 6
│   ├── build.py                          # solution pass, warnings
│   ├── project_view.py                   # new: project link graph, projects summary
│   ├── queries.py                        # level option, projects question, resolve() for .sln/.csproj, overview
│   └── results.py                        # Link.declared, Item.declared_only, ProjectSummary, text rendering
├── cli/__init__.py                       # --level, projects, warnings
└── mcp/server.py                         # projects tool, level argument
backend/tests/                            # contract, unit (test_sln.py, test_project_view.py), golden, integration
fixtures/repos/csharp-multiproject/       # + solutions, loop projects; expected.json, queries.json by hand
fixtures/repos/csharp-types/queries.json  # + project-level answers
```

**Structure Decision**: the project view is a separate module inside `graph/` so `queries.py` keeps one
responsibility per function; the solution readers sit next to the `.csproj` reader.

## Commits

One commit per task from `tasks.md`, pushed right after it, authored by the user only.

## Complexity Tracking

No constitution violations to justify.
