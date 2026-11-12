# Data Model: C# Analysis, Slice 2 (Schema v5)

Changes relative to schema v4 ([007 data-model](../007-csharp-analysis/data-model.md)). Machine-checked contract:
[contracts/graph.schema.json](contracts/graph.schema.json). Research items R1–R10: [research.md](research.md).

## Document

| Field | Change |
|---|---|
| `schema_version` | `5` |
| `extractors` | `csharp-adapter` `0.2.0`, `csharp-resolver` `0.2.0`, `csproj-reader` `0.2.0`; new `dotnet-types` `10.0.0`, `dotnet-implicit-usings` `10.0.100` |

## Type-reference edge (new)

| Field | Value |
|---|---|
| `type` | `type_reference` |
| `source` | `file:<path>` (C#) |
| `target` | `file:<path>` of the declaring file, or `unresolved:dotnet:<name>` for an ambiguous name |
| `symbol` | full name of the first type referenced in the target (`App.Services.Mailer`), or the name as written for `ambiguous` |
| `form` / `type_only` | `static` / `false`; no `directive`, no `alias` |
| `line`, `column` | first reference to the target with the edge's confidence |
| `snippet_hash` | hash of that source line, trimmed |
| `confidence` / `reason` | `resolved`; `heuristic` + `partial_type` or `msbuild_condition`; `unresolved` + `ambiguous` |
| `extractor` | `csharp-adapter@0.2.0` |

At most one edge per (source, target). No self-edges.

## `using` edges (changed)

Slice-1 edges from a `using` (or namespace alias) directive to `file:` targets are removed when at least one type
reference in the file (for a global using: in the project) resolved through that directive (R7). Edges to
`ext:dotnet:`, `ext:nuget:`, `unresolved:dotnet:` and all `using_static` edges are unchanged.

## Coverage (changed)

| Field | Value |
|---|---|
| `unresolved_type_names` | integer ≥ 0, only on `analyzed` C# files: distinct simple names in type positions matching no repository or base-library type (R8) |

## Internal entities (not serialized)

- **TypeRef** (per occurrence): name as written (dots, no generic arguments), `rooted` (`global::`), kind
  (`type` | `qualifier`), enclosing namespace chain, enclosing type-parameter names, line, column, line text.
- **ProjectUsings** (per project): namespaces, aliases (`name → target`), static types; each with `conditional`
  and `origin` (`global_using:<path>:<line>`, `implicit:<sdk>`, `using_item:<path>`, `props:<path>`).
- **BaseLibrary**: `framework → namespace → frozenset(type names)` from `dotnet_types.txt`.
- **ImplicitUsings**: `sdk group → namespaces` from `implicit_usings.txt`.

## Resolution of a type reference (R2)

For simple name `X` in namespace chain `[A.B, A, ""]`, at each level `N` in order:

| Step | Candidates | Result |
|---|---|---|
| 1 | repository types `N.X` in visible scopes | found → stop |
| 2 | aliases named `X` declared at level `N` (at `""`: file aliases + project global aliases) | alias target resolved as a full name → stop |
| 3 | for each namespace `U` imported at level `N` (at `""`: file usings + project global usings): repository types `U.X` and base-library types `U.X` of the project's frameworks | one distinct full name → stop; two or more → `unresolved: ambiguous`, stop |

Nothing found at any level: `type` kind → counted in `unresolved_type_names`; `qualifier` kind → ignored.

A found repository type declared in 1 file → `resolved` edge; in several (`partial`) → `heuristic: partial_type`
edges to each. A found base-library type → no edge. Anything reached through a conditional using or a project
visible only through a conditional reference → `heuristic: msbuild_condition` (reason priority from slice 1).

Qualified names follow R2 (alias substitution of the first segment, enclosing-namespace prefixes, as written,
imported prefixes); attributes also try `XAttribute`.

## Project usings (R4, R5)

Effective global usings of a project, in this order:

1. implicit usings of the SDK group if `ImplicitUsings` is `enable`/`true` (from `Directory.Build.props`, then the
   project; the project value wins);
2. `<Using>` items from `Directory.Build.props`, then from the project;
3. `global using` directives in the project's `.cs` files;
4. `<Using Remove>` items (props, then project) remove matching namespaces from 1–2.

Project-less files: only their own `global using` directives (no implicit usings).
