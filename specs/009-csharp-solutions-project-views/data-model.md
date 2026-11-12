# Data Model: C# Analysis, Slice 3 (Schema v6)

Changes relative to schema v5 ([008 data-model](../008-csharp-type-references/data-model.md)). Contract:
[contracts/graph.schema.json](contracts/graph.schema.json). Research: [research.md](research.md).

## Graph document

| Item | Change |
|---|---|
| `schema_version` | `6` |
| `extractors` | adds `sln-reader` `0.1.0` |
| Solution node (new) | `{"id": "solution:<path>", "kind": "solution", "path": "<path ending .sln or .slnx>"}`, one per walked solution file (also with `parse_error`) |
| `solution_member` edge (new) | source `solution:…`; target `project:…` or `unresolved:dotnet:…`; `symbol` = path as written; `form` `static`, `type_only` false; line/column/snippet of the entry; extractor `sln-reader@0.1.0`; confidence `resolved` or `unresolved` with `not_found`, `msbuild_property` or `not_csharp` (new) |
| Coverage | `.sln`/`.slnx` stay `csharp` `not_code`; `parse_error` flag when unreadable as a solution (R1, R2) |

## Query-time entities (not stored)

### Project link (R4)

| Field | Meaning |
|---|---|
| `source`, `target` | `project:` ids, or a `project:` source and an `ext:nuget:` target |
| `edges` | evidence: file-level `imports`/`type_reference` edges between files of the two projects (or to the package), sorted by edge sort key |
| `declared` (new, optional) | `project_reference` / `package_reference` edges for the pair, sorted |
| `confidence` | strongest evidence confidence; declared edge's confidence when there is no evidence |
| `declared_only` (new, optional on items) | `true` when `edges` is empty |

### Projects answer entry (R6)

| Field | Meaning |
|---|---|
| `project` | `project:<path>`, or `null` for project-less C# files |
| `path` | `.csproj` path, or `null` |
| `solutions` | sorted `solution:` ids with a resolved membership edge |
| `files` | number of C# file nodes owned |
| `references` | sorted `project:` ids from resolved or heuristic `project_reference` edges |
| `packages` | sorted `ext:nuget:` ids from `package_reference` edges and from code edges |
| `uses`, `used_by` | sorted `project:` ids linked by code evidence |

Ordering: entries by `path`, the `null` entry last. Empty list for graphs without project nodes.

## Validation

- Loader: a `solution_member` edge needs a solution-node source; solution nodes may not be the source of any other
  edge type (also enforced by the schema).
- Project-level questions on a target that is not a project, a `.csproj` path or a C# file → `NodeNotFound`,
  status `not_a_project`.
