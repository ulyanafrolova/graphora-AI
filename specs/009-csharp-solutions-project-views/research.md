# Research: C# Analysis, Slice 3

Decisions R1–R8, referenced from [plan.md](plan.md) and [data-model.md](data-model.md).

## R1. Reading `.sln` (text format)

- **Decision**: a line-based reader (`sln-reader@0.1.0`) that decodes UTF-8 (BOM allowed; other encodings →
  `parse_error`) and requires the `Microsoft Visual Studio Solution File` header line within the first 3 lines
  (otherwise `parse_error`). It takes only lines matching
  `Project("{TYPE}") = "Name", "Path", "{GUID}"`, recording the type GUID, path as written, 1-based line and column of
  the line start, and the line text for the snippet hash. `GlobalSection`, configurations, platforms and
  `ProjectSection(SolutionItems)` are ignored.
- Type handling: solution folder GUID `2150E333-8FDC-42A3-9474-1A3956D46DE8` → skipped; a path ending in `.csproj`
  → C# project (any GUID); anything else → `not_csharp`.
- **Rationale**: the format is line-oriented and stable since VS 2005; a regular line match is exact and needs no
  dependency. The path, not the GUID, decides C#, because SDK-style projects use two different C# GUIDs.
- **Alternatives**: a full grammar (no benefit for the fields used); running `dotnet sln list` (forbidden by
  constitution I).

## R2. Reading `.slnx` (XML format)

- **Decision**: the slice-1 expat approach (DTD refused): every `Project` element with a `Path` attribute anywhere
  under `Solution`, with line and column of the element and its start tag as snippet. `Folder` elements create
  nothing; `File` elements (solution items) are ignored. Malformed XML or a `DOCTYPE` → `parse_error`.
- **Rationale**: `.slnx` is the new XML solution format (Visual Studio 17.13+, `dotnet sln` from .NET 9); same
  safety rules as `.csproj`.

## R3. Solution membership resolution

- **Decision**: per entry, in order: `$(` in the path → `unresolved: msbuild_property`; not a `.csproj` (folder
  entries already skipped) → `unresolved: not_csharp` with the normalized path as reference; `\` → `/`, join with the
  solution's folder, normalize; outside the root → `unresolved: not_found` (reference = path as written);
  a walked `.csproj` → `resolved` edge to `project:<path>`; otherwise `unresolved: not_found` (reference = normalized
  path). `symbol` = path as written.
- **Rationale**: same rules and reasons as slice-1 `ProjectReference`, plus `not_csharp` so non-C# projects are
  visible but never confused with missing ones.

## R4. Project link computation (query time)

- **Decision**: `graph/project_view.py` builds, once per `GraphIndex` and lazily, a project-level link graph:
  - file → project map from C# file nodes' `project`;
  - for every non-`unresolved` edge of type `imports` or `type_reference` between files of two different projects:
    evidence on the link `(source project, target project)`;
  - for every `project_reference` edge that is not `unresolved`: the link's `declared` edges;
  - packages: `package_reference` edges (declared) and file edges to `ext:nuget:` (evidence) aggregated to the source
    file's project;
  - links are inserted in sorted order (NetworkX, as in 004 research R3), evidence and declared edges sorted by the
    existing edge sort key.
  Link confidence = strongest evidence confidence; a declared-only link takes the declared edge's confidence and is
  flagged `declared_only`.
- **Rationale**: nothing derived is stored (clarification), the result is a pure function of the document, and the
  existing `Link`/`Item`/`Answer` shapes carry it with two optional fields.

## R5. Questions at project level

- **Decision**:
  - `dependencies` / `dependents`: one item per neighbouring project or package, chain = the one project link;
  - `impact`: BFS over reversed code links (declared-only links excluded: they are not used by code), nearest first,
    chain of project links, `max_depth` honoured;
  - `cycles`: strongly connected components of code links (declared-only excluded), each with one shortest example
    cycle, using the existing helpers;
  - target resolution: a `.csproj` path or `project:` id; a C# file path is mapped to its project; anything else →
    the existing `NodeNotFound` with status `not_a_project`;
  - `--symbol`, `--follow-barrels` and `--no-type-only` do not apply at project level → the existing usage error.
- **Rationale**: same questions, same answer shape; agents and people do not learn a new API.

## R6. `projects` question

- **Decision**: a new question (`graphora query <graph> projects`, MCP tool `projects`) listing, per project node in
  path order: `project`, `path`, `solutions` (sorted ids), `files` (count of C# files owned), `references` (declared
  project ids, resolved only), `packages` (`ext:nuget:` ids, declared or used), `uses` / `used_by` (project ids linked
  by code). A final entry with `project: null` counts project-less C# files. Non-C# graphs → empty list.
- **Rationale**: FR-005; the overview agents need before asking project-level questions.

## R7. Schema v6 and consumers

- **Decision**: [contracts/graph.schema.json](contracts/graph.schema.json): `schema_version` 6, `solutionNode`
  (`solution:<path>`, path ending `.sln`/`.slnx`), edge type `solution_member` (solution → project or
  `unresolved:dotnet:`), reason `not_csharp`. Consumers: model, serializer, loader (solution source check), queries
  (`resolve()` accepts `.sln` paths; `_kind` adds `solution`), overview (`nodes.solution` count), store validation,
  MCP, tests and all fixtures. The draft accepts five current fixture outputs with the version set to 6 and rejects 7
  invalid samples.

## R8. Fixtures and performance

- **Decision**: `csharp-multiproject` gains `Graphora.sln` (backslash paths, solution folder, missing project,
  `.fsproj`, `$(…)` path) and `Graphora.slnx` (same projects minus one, so one project is in one solution only) plus a
  project-level cycle between two new small projects; `csharp-types` gets project-level `queries.json` entries (code
  links via type references and fallback, declared-unused reference). Performance: project-level `impact` and
  `cycles` on the 1,000-file generated repo under 2 s (SC-005), in the existing slow test file.
