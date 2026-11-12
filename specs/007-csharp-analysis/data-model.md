# Data Model: C# Analysis, Slice 1 (Schema v4)

Changes relative to schema v3 ([003 data-model](../003-ts-js-analysis/data-model.md) plus the v3 skip reason
`unreadable_dir`). The machine-checked contract is [contracts/graph.schema.json](contracts/graph.schema.json).
Research items are R1–R11 in [research.md](research.md).

## Document

| Field | Change |
|---|---|
| `schema_version` | `4` |
| `extractors` | adds `csharp-adapter`, `csharp-resolver`, `csproj-reader` (all `0.1.0`) and `dotnet-namespaces` (`10.0.0`) |

## Nodes

### File node (C#)

| Field | Value |
|---|---|
| `id` | `file:<path>` |
| `language` | `csharp` |
| `definitions` | see [Definition](#definition-c) |
| `project` | `project:<path to .csproj>` or `null` (project-less or `ambiguous_project`); required for C#, forbidden for other languages |
| `exports` | absent (TS/JS only) |

### Definition (C#)

| Field | Value |
|---|---|
| `kind` | `class`, `struct`, `record` (also `record struct`), `interface`, `enum`, `delegate`, `method` |
| `name` | fully qualified: namespace + enclosing types + name, `.`-joined, generic parameters dropped (`App.Outer.Inner`, `App.Program.Main`); global-namespace types have no prefix |
| `line` | 1-based line of the declaration's name |
| `exported_as` | absent |

Each `partial` part is a separate definition in its own file. Methods are listed for every declared type,
including nested ones; constructors, properties, fields, events and local functions are not.
Sort order is unchanged: `(line, name)`.

### Project node (new)

| Field | Value |
|---|---|
| `id` | `project:<path>`; path ends in `.csproj` |
| `kind` | `project` |
| `path` | repository-relative path of the `.csproj` |

One per walked `.csproj`, including ones with `parse_error` (they still own files, FR-009).

### External node

| Ecosystem | Id | Category | Source |
|---|---|---|---|
| `dotnet` (new) | `ext:dotnet:<namespace>` | `stdlib` | base-library namespace list (R6) |
| `nuget` (new) | `ext:nuget:<package id>` | `third_party` | `PackageReference` (R7) |

### Unresolved node

Ecosystem `dotnet` (new) for every C# placeholder. `reference` is:

- the namespace or type name as resolved for a `using` (after `global::` and generic arguments are dropped);
- the repository-relative path tried for a `ProjectReference` that does not exist, or the `Include` text as
  written when it is outside the root or contains `$(`, `@(`, `*` or `?`;
- the `Include` text as written for a `PackageReference` with `$(…)`.

## Edges

### Common rules (v4)

- Every edge keeps all v3 required fields.
- `resolved` → no `reason`; `heuristic` → reason from {`namespace_spread`, `partial_type`, `package_prefix`,
  `msbuild_condition`}; `unresolved` → reason from {`not_found`, `relative_beyond_top`, `namespace_package`,
  `dynamic`, `workspace_package`, `not_referenced`, `no_types`, `ambiguous`, `msbuild_property`}.
- `source` is a file node for `imports`/`reexports`, a project node for `project_reference`/`package_reference`.

### `using` edge (C#)

| Field | Value |
|---|---|
| `type` | `imports` |
| `form` / `type_only` | `static` / `false` |
| `directive` (new) | `using`, `using_static` or `using_alias` |
| `global_using` (new) | `true` for `global using`; present exactly when `directive` is |
| `symbol` | resolved namespace (`using`) or full type name (`using_static`, type alias); for a namespace alias, the namespace |
| `alias` | alias name, only and always for `using_alias` |
| `line`, `column` | start of the `using_directive` |
| `snippet_hash` | hash of the directive text |
| `extractor` | `csharp-adapter@0.1.0` |

One edge per target: a directive resolved to N declaring files yields N edges with the same position.

### Project reference edge (new)

| Field | Value |
|---|---|
| `type` | `project_reference` |
| `source` | `project:<referencing .csproj>` |
| `target` | `project:<referenced .csproj>` or `unresolved:dotnet:…` |
| `symbol` | `Include` value as written (e.g. `..\Core\Core.csproj`) |
| `form` / `type_only` | `static` / `false` |
| `line`, `column`, `snippet_hash` | start tag of the item in the `.csproj` |
| `extractor` | `csproj-reader@0.1.0` |

### Package reference edge (new)

Same as the project reference edge with `type` `package_reference` and target `ext:nuget:<id>` or
`unresolved:dotnet:…`.

## Coverage

| Item | Value |
|---|---|
| `.cs` | language `csharp`, status `analyzed`; flags `parse_error`, `unreadable`, `ambiguous_project` (new) |
| `.csproj` | language `csharp`, status `not_code`; flag `parse_error` for malformed XML or a `DOCTYPE` |
| `.sln`, `Directory.Build.props`, `Directory.Packages.props` | language `csharp`, status `not_code` (read in later slices) |
| `.cshtml`, `.razor`, `.fs`, `.vb` | `detected_only` (`razor`, `fsharp`, `vb`) |
| `bin/`, `obj/` next to a `.csproj` | skipped, reason `excluded_dir` (R3) |

## Internal entities (not serialized)

- **CsFacts** (per file): namespace declarations; type declarations `(kind, full name, namespace, line,
  partial)`; method declarations; using directives `(form, global, alias, target text or non-name kind,
  enclosing namespace, line, column, text)`; `has_error`.
- **ProjectFacts** (per `.csproj`): `sdk`, `use_wpf`, `use_windows_forms`, items
  `(kind, include, conditional, line, column, text)`, `has_error`.
- **Scope**: a project or the project-less group: `namespaces: name → sorted files`,
  `types: full name → sorted files`.
- **Visibility**: per scope, `reachable_unconditional` and `reachable_any` (sorted scope lists, R4).

## Resolution

### Ownership (R3)

For `.cs` file `f`: walk folders from `dirname(f)` up to the root; at the first folder that holds `.csproj`
files, one file → owner; two or more → no owner + `ambiguous_project`. None found → project-less.

### `ProjectReference Include="x"`

| Condition (first match wins) | Result |
|---|---|
| `x` contains `$(`, `@(`, `*` or `?` | `unresolved: msbuild_property` |
| `x` (with `\` → `/`, joined to the `.csproj` folder and normalized) leaves the root | `unresolved: not_found` |
| normalized path is a walked `.csproj` | `resolved` → `project:<path>`, or `heuristic: msbuild_condition` if conditional |
| otherwise | `unresolved: not_found` |

### `PackageReference Include="x"`

`$(…)` → `unresolved: msbuild_property`; otherwise → `ext:nuget:x`, `resolved`, or
`heuristic: msbuild_condition` if conditional. `Update`/`Remove` items are ignored.

### `using` directives (R5)

Candidates: inside namespace `A.B` a name `X` is tried as `A.B.X`, `A.X`, `X`; at file level, in a
`global using`, or with `global::`, only `X`. "Declared" means declared in any scope of the repository.

| Directive | Rule (first match wins) | Result |
|---|---|---|
| `using N;` / namespace alias | first candidate with declaring files in a visible scope | edges to those files (minus self): 1 → `resolved`, >1 → `heuristic: namespace_spread` |
| | first candidate declared in the repository, but only outside visible scopes | `unresolved: not_referenced` |
| | first candidate the repository declares only as a parent namespace | `unresolved: no_types` |
| | `X` in the project's base-library list (R6) | `resolved` → `ext:dotnet:X` |
| | `X` equals or starts with `id.` for exactly one package id of the project (case-insensitive) | `heuristic: package_prefix` → `ext:nuget:id` |
| | several package ids match | `unresolved: ambiguous` |
| | otherwise | `unresolved: not_found` |
| `using static T;` / type alias | first candidate that is a type with declaring files in a visible scope | 1 file → `resolved`; several (`partial`) → `heuristic: partial_type` |
| | otherwise | namespace part of `X` through the `using N;` rows 2–7 |
| alias to tuple/array/pointer/keyword type | — | no edge |

A target reachable only through conditional references downgrades `resolved` to
`heuristic: msbuild_condition`. When several heuristic reasons apply, the first of `partial_type`,
`namespace_spread`, `package_prefix`, `msbuild_condition` is kept.

## Validation rules (enforced by schema and loader)

- Every rule in [contracts/graph.schema.json](contracts/graph.schema.json); the loader (`graph/load.py`) also checks
  that every edge source exists and is a file node (for `imports`/`reexports`) or a project node (for
  `project_reference`/`package_reference`), and that only `unresolved` edges point to placeholders.
