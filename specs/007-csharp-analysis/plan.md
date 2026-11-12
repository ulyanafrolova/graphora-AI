# Implementation Plan: C# Analysis, Slice 1 (Graph Schema v4)

**Branch**: `docs/constitution-csharp` (PR #22, issue #19) | **Date**: 2026-11-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-csharp-analysis/spec.md`

## Summary

This slice makes `graphora analyze` fully analyze C# next to Python and TS/JS, and moves the graph format to
schema v4.

What the output gains:

- a file node for every `.cs` file, with its types and methods under fully qualified names and its owning project;
- a project node for every `.csproj`, with `project_reference` and `package_reference` edges;
- one `imports` edge per `using` directive and target file, with `directive` and `global_using` fields;
- `ext:dotnet:` base-library namespaces, `ext:nuget:` packages and `unresolved:dotnet:` placeholders;
- `heuristic` edges with a reason (`namespace_spread`, `partial_type`, `package_prefix`, `msbuild_condition`).

How it works:

- **Parsing.** Tree-sitter with the pinned C# grammar extracts namespaces, types, methods and `using`
  directives (R1).
- **Project files.** An expat-based reader reads `.csproj` files as data, with line positions, and refuses DTDs
  (R2). Each `.cs` file belongs to the nearest `.csproj`; `bin/` and `obj/` next to a `.csproj` are skipped (R3).
- **Resolution.** A per-project namespace and type index, visible through transitive project references (R4),
  resolves each directive by the fixed rules in [data-model.md § Resolution](data-model.md#resolution) (R5),
  with a shipped .NET 10 namespace list (R6).
- **No guessing.** No `dotnet`, MSBuild or NuGet; no `$(…)` expansion; ambiguity is `unresolved`, and links that
  depend on an unread condition or a naming convention are `heuristic` with a reason.

## Technical Context

**Language/Version**: Python ≥ 3.12, developed on 3.14 (unchanged)

**Primary Dependencies**: adds `tree-sitter-c-sharp==0.23.5` to the existing pinned `tree-sitter==0.25.2` and
grammars. `.csproj` files are read with the standard library `xml.parsers.expat`. No new dev dependency.
Research: [R1–R11](research.md)

**Storage**: unchanged (one JSON file, optional PostgreSQL store from 005, which only sees a new schema version)

**Testing**: pytest: golden (3 new fixtures, all existing ones migrated to v4), contract (v4 accept/reject
samples), unit (C# extract, csproj reader, ownership, index, resolver, walk rule, loader, queries), integration
(safety, CLI warning, store round trip, performance)

**Target Platform**: macOS and Linux developer machines and CI. No .NET SDK required

**Project Type**: CLI and HTTP API inside the `backend` package

**Performance Goals**: about 1,000 `.cs` files across 20 projects in under 30 seconds on a laptop (SC-005)

**Constraints**:

- byte-identical output;
- no execution: no `dotnet`, MSBuild, NuGet or subprocess; no DTD or entity expansion;
- no reads outside the root or inside skipped folders; `<Import>` and `$(…)` never followed;
- 001 limits unchanged.

**Scale/Scope**: fixtures have 15–40 files each; real targets have up to 5,000 files and tens of projects

No open questions remain. During planning the spec was corrected (see its Clarifications section): base-library
namespaces use ecosystem `dotnet` apart from `nuget` packages (R7), the package match gets reason
`package_prefix`, a `using` inside a namespace block follows the compiler's lookup (R5), and aliases to tuple or
keyword types create no edge.

## Constitution Check

*GATE: checked before Phase 0, and re-checked after Phase 1.* Constitution version 1.1.0.

| Principle | How this plan complies | Status |
|---|---|---|
| I. Never execute analyzed code | `.cs` files are parsed by Tree-sitter only. `.csproj` files are read by expat as data; a `DOCTYPE` makes the file `parse_error`, so no entity is expanded; `<Import>`, `$(…)`, `@(…)` and wildcards are never evaluated or followed. No `dotnet`, MSBuild, NuGet or subprocess. Resolution only looks up walked files, so `..\..\outside` references and skipped folders are never read. A new safety test covers these cases | ✅ |
| II. Deterministic output | Sorted index tuples, path-ordered projects and directives, fixed candidate order, fixed reason priority, shipped namespace list (R6, R11). Determinism tests cover the new fixtures | ✅ |
| III. Provenance on every edge | `using` edges carry all v3 fields; `.csproj` edges point at the item's line and column with a snippet hash of its start tag and extractor `csproj-reader@0.1.0`. The schema rejects any edge missing a field | ✅ |
| IV. Honest confidence | Ambiguity, missing targets and unread MSBuild values are `unresolved` with a reason; namespace spread, `partial` types, package-name conventions and conditional references are `heuristic` with a reason; the schema now requires a reason on `heuristic` edges. Razor, F# and VB stay `detected_only` | ✅ |
| V. Facts by code | No LLM in this slice | ✅ (n/a) |
| VI. Analyzed content is data | No model reads content. Snippets are hashed, not copied | ✅ (n/a) |
| VII. One graph query layer | Model, serializer, loader and queries stay in `graph/`. Schema bumped to v4; every consumer (serializer, loader, queries, store validation, tests, all fixtures) changes in this PR (R9) | ✅ |
| VIII. Golden tests | Three new hand-written fixtures plus migrated ones; repeat-run test | ✅ |
| Tech constraints | Python, `uv`, Tree-sitter; C# is in the language list since constitution 1.1.0 (this PR) | ✅ |
| Workflow | One branch and one PR for the whole C# feature (issue #19); the spec covers slice 1 only; slices 2–3 follow on the same branch | ✅ |

**Re-check after Phase 1:** no violations. The draft [contracts/graph.schema.json](contracts/graph.schema.json)
accepts the current output of `py-flat`, `ts-app`, `ts-monorepo` and `mixed-fullstack` (with the version set to
4) and a C# sample document, and rejects 21 invalid samples, including:

- a `heuristic` edge without a reason, or with an `unresolved`-only reason;
- `directive` without `global_using` (and the reverse), `using_alias` without `alias`, `alias` on a plain `using`;
- a `project_reference` from a file, a `package_reference` to an npm package, an `imports` edge from a project;
- a C# file without `project` or with `exports`, a TS file with `project`, a Python `record`;
- a `dotnet` node with category `third_party`, a `nuget` node with `stdlib`, an `unresolved:nuget:` placeholder;
- a project node whose path is not a `.csproj`, and a v3 document.

## Project Structure

### Documentation (this feature)

```text
specs/007-csharp-analysis/
├── spec.md
├── plan.md                # this file
├── research.md            # R1–R11
├── data-model.md          # v4 changes, C# nodes/edges, resolution tables
├── quickstart.md          # validation guide
├── contracts/
│   ├── graph.schema.json  # v4, becomes schema/graph.schema.json
│   └── cli.md             # changes to the analyze, query and API contracts
├── checklists/requirements.md
└── tasks.md               # /speckit-tasks
```

### Source Code (repository root)

```text
schema/
└── graph.schema.json                  # v3 → v4, copied from contracts/

backend/
├── pyproject.toml                     # + tree-sitter-c-sharp==0.23.5
├── scripts/gen_dotnet_namespaces.py   # regenerates dotnet_namespaces.txt from *.Ref packages (never run by tests)
├── src/graphora/
│   ├── adapters/
│   │   ├── csharp/
│   │   │   ├── __init__.py            # csharp-adapter@0.1.0
│   │   │   └── extract.py             # namespaces, types, methods, using directives, parse errors
│   │   └── msbuild/
│   │       ├── __init__.py            # csproj-reader@0.1.0
│   │       └── csproj.py              # expat reader: items, Sdk, UseWPF/UseWindowsForms, conditions, positions
│   ├── resolve/
│   │   ├── csharp.py                  # ownership, scopes, visibility, using + reference resolution
│   │   └── data/dotnet_namespaces.txt # dotnet-namespaces@10.0.0
│   ├── detect/languages.py            # .cs analyzed; .csproj/.sln/Directory.*.props markers; .cshtml/.razor/.fs/.vb detected_only
│   ├── ingest/walk.py                 # bin/obj skipped next to a .csproj
│   ├── graph/
│   │   ├── build.py                   # C# pass; csproj warnings; extractor versions
│   │   ├── model.py                   # ProjectNode, project on FileNode, directive/global_using, new enums, heuristic reason rule
│   │   ├── serialize.py               # SCHEMA_VERSION = 4, new fields
│   │   ├── load.py                    # project nodes, project-sourced edges, csharp language
│   │   ├── queries.py                 # resolve() for .csproj paths and nuget/dotnet names
│   │   └── results.py                 # names for project:/dotnet:/nuget: ids
│   └── cli/__init__.py                # warning message chosen by file type
└── tests/
    ├── conftest.py                    # projection gains project, directive, global_using
    ├── golden/test_fixtures.py        # C# fixtures, extractor checks
    ├── contract/test_schema.py        # v4 accept/reject samples
    ├── integration/
    │   ├── test_safety_cs.py          # DOCTYPE/entities, outside references, <Import>, no subprocess
    │   └── test_performance.py        # + ~1,000 generated .cs files in 20 projects
    └── unit/
        ├── test_cs_extract.py
        ├── test_csproj.py
        ├── test_cs_resolve.py
        ├── test_walk.py               # + bin/obj rule
        ├── test_load.py               # + v4 cases
        ├── test_extractor_versions.py # + extractor_versions.json entries for the new extractors
        └── test_index.py              # + project and C# names in resolve()

fixtures/repos/
├── (all existing)/expected.json       # schema_version 4 only
├── csharp-basic/{repo/, expected.json, queries.json}
├── csharp-multiproject/{repo/, expected.json, queries.json}
└── csharp-edge/{repo/, expected.json, queries.json}
```

**Structure Decision**:

- This extends the 003 layout with a C# adapter, an MSBuild reader and a C# resolver. `adapters/msbuild/` is its
  own package because slices 2–3 add `Directory.Build.props` and `.sln` readers there.
- No new top-level folders. `frontend/` does not exist yet; the schema stays its contract. The HTTP API needs no
  code change beyond the query layer.
- `006-mcp-server` (unmerged) consumes the schema; whichever PR merges second rebases onto the other (R9).

## Commits

One commit per task from `tasks.md`, pushed right after it, authored by the user only.

## Complexity Tracking

No constitution violations to justify.
