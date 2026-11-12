# Research: C# Analysis, Slice 1

Each item gives a Decision, the Rationale and the Alternatives considered. Items are referenced as R1–R11 from
[plan.md](plan.md) and [data-model.md](data-model.md).

## R1. Grammar: `tree-sitter-c-sharp==0.23.5`

- **Decision**: add `tree-sitter-c-sharp==0.23.5` (released 2026-04-14), pinned exactly like the other grammars
  (issue #8). It loads with the existing `tree-sitter==0.25.2` (grammar ABI 15). The adapter uses these node
  types, checked against a probe file during planning:
  - `compilation_unit`, `namespace_declaration` (block; `name` is `identifier` or `qualified_name`, nested blocks
    allowed), `file_scoped_namespace_declaration`;
  - `class_declaration`, `struct_declaration`, `record_declaration` (also `record struct`),
    `interface_declaration`, `enum_declaration`, `delegate_declaration`, `method_declaration`, all with a `name`
    field; members live in `declaration_list`;
  - `using_directive`: an optional `name` field is the alias; the anonymous tokens `global` and `static` mark the
    form; the target is `identifier`, `qualified_name` (may contain `generic_name` and `alias_qualified_name`
    for `global::`), or another type node (`tuple_type`, `array_type`, `pointer_type`, `predefined_type`);
  - `preproc_if` / `preproc_else` wrap directives and types without hiding them, so all branches are seen;
  - `ERROR` / `MISSING` nodes set `has_error` → coverage flag `parse_error`, and readable parts are kept.
- **Rationale**: the same toolchain as Python and TS/JS; no .NET SDK needed; tolerant parsing of broken files.
- **Alternatives**: Roslyn (needs .NET, i.e. running a toolchain on the machine and loading project files:
  rejected by constitution I and the "no .NET installed" requirement, FR-016); regular expressions (cannot tell
  a `using` directive from a `using` statement, nor handle nesting and preprocessor blocks).

## R2. Reading `.csproj` files: expat with DTDs refused

- **Decision**: a small reader on top of `xml.parsers.expat` (standard library). It:
  - refuses any `<!DOCTYPE` (and so all entity declarations) by raising in `StartDoctypeDeclHandler`: the file is
    then `parse_error`, which defeats entity-expansion bombs and external entities;
  - records each element's local name (namespace prefix dropped, MSBuild 2003 namespace allowed), attributes,
    1-based line, column converted to the project's column convention (`adapters/position.py`), and the raw
    start-tag text for the snippet hash;
  - keeps only `ItemGroup` children `ProjectReference`, `PackageReference` (with `Include`, never `Update` or
    `Remove`), `FrameworkReference`, plus the `Project` root's `Sdk` attribute and the properties `UseWPF` and
    `UseWindowsForms` (R6);
  - marks an item as conditional when it or its `ItemGroup` has a `Condition` attribute;
  - splits `Include="a;b"` into one item per entry, all with the same position;
  - never follows `<Import>`, never reads another file, never expands `$(…)` or `@(…)`, never globs.
- **Rationale**: `xml.etree` gives no line numbers, which provenance needs (constitution III); expat gives exact
  positions. Refusing DTDs is simpler and stricter than `defusedxml`, needs no new dependency, and real project
  files never contain one.
- **Alternatives**: `defusedxml` (new dependency, still no line numbers via ElementTree); `lxml` (native
  dependency; same position trick needed); MSBuild evaluation (forbidden: constitution I).

## R3. Project ownership and the `bin`/`obj` rule

- **Decision**:
  - Ownership is computed after the walk from the list of walked files: for each `.cs` file, look in its folder
    and then each parent folder for `.csproj` files; the first folder with exactly one wins; a first folder with
    two or more gives no project plus the coverage flag `ambiguous_project` and stops the search.
  - The walker skips a folder named `bin` or `obj` with reason `excluded_dir` when the folder being listed (its
    parent) contains a regular file ending in `.csproj`. The walker already lists and sorts each folder's
    entries before descending, so the check costs nothing extra.
  - Archive extraction (`ingest/archive.py`) is unchanged: `bin`/`obj` are extracted and then skipped by the
    walker. The dirty-tree snapshot hash (`ingest/snapshot.py`) already ignores every folder the walker reports
    as skipped, so no name-only rule is needed there.
- **Rationale**: `bin/` is a common real folder in Python and shell repositories (`tools/bin/`), so a name-only
  rule would hide code. Next-to-a-`.csproj` matches where MSBuild puts its output by default.
- **Alternatives**: add `bin`/`obj` to `EXCLUDED_DIRS` (hides scripts in non-.NET repos); a separate skip reason
  (`build_output`) (needs another schema value for no user benefit; `excluded_dir` already means "known
  generated or vendored folder").

## R4. Namespace index and visibility

- **Decision**:
  - The index maps each namespace to the sorted tuple of files that declare at least one type directly in it,
    and each fully qualified type name (namespace + enclosing types, generic arity dropped) to the sorted tuple
    of declaring files. Built per project ("scope"), plus one scope for project-less files.
  - A project's visible scopes are itself plus every project reachable through `ProjectReference` edges
    (transitive, as SDK-style projects behave by default), computed once per project in sorted order.
  - Reachability is computed twice: through unconditional references only, and through all references. A target
    file reachable only through a conditional reference makes its edge `heuristic` with reason
    `msbuild_condition`.
  - "Declared in the repository" (for `not_referenced`, FR-013 step 2) uses the union of all scopes.
- **Rationale**: matches what the compiler can see without guessing which configuration builds; per-project
  caching keeps resolution linear in the number of `using` directives (SC-005).
- **Alternatives**: one repository-wide index (would point `using` at files the compiler cannot see, i.e. wrong
  facts); direct references only (wrong for SDK-style projects, which flow references transitively).

## R5. Resolving `using` directives

- **Decision** (full table in [data-model.md § Resolution](data-model.md#resolution)):
  - **Name handling**: `global::` is dropped and disables the relative lookup; generic arguments are dropped
    (`List<int>` → `List`); whitespace inside the name is ignored.
  - **Relative lookup**: a directive inside namespace block `A.B` tries `A.B.X`, `A.X`, then `X`; the first
    candidate that the repository declares (namespace for plain using, type or namespace for alias, type for
    static) is used. Directives at file level and in `global using` only try `X`. This is the compiler's rule,
    so it is not a guess.
  - **Plain using** → FR-013 steps 1–5. **Static using** and **type alias** → type lookup first (FR-014), then
    the namespace part through steps 2–5. **Namespace alias** → like plain using.
  - **No self-edges**; a namespace that the repository declares only as a parent of other namespaces gives
    `unresolved: no_types`.
  - **Alias to a tuple, array, pointer or keyword type** → no edge (spec FR-007, corrected during planning).
  - **Reason priority** when several heuristic causes apply to one edge: `partial_type`, then
    `namespace_spread`, then `package_prefix`, then `msbuild_condition`.
- **Rationale**: every step is a fixed rule over sorted data; anything that would need type inference is left
  `heuristic` with a reason or `unresolved`.
- **Alternatives**: treat a `using` inside a namespace like a file-level one (simpler, but turns common code
  such as `namespace Co.App { using Services; }` into false `not_found`).

## R6. Base-library namespace list: `dotnet-namespaces@10.0.0`

- **Decision**: ship `backend/src/graphora/resolve/data/dotnet_namespaces.txt`, one `framework namespace` pair per
  line, sorted, for the shared frameworks of .NET 10 (LTS):
  - `Microsoft.NETCore.App`: applies to every project and to project-less files;
  - `Microsoft.AspNetCore.App`: applies when the project's `Sdk` is `Microsoft.NET.Sdk.Web`,
    `Microsoft.NET.Sdk.Razor` or `Microsoft.NET.Sdk.BlazorWebAssembly`, or it has
    `<FrameworkReference Include="Microsoft.AspNetCore.App" />`;
  - `Microsoft.WindowsDesktop.App`: applies when `UseWPF` or `UseWindowsForms` is `true`.

  `backend/scripts/gen_dotnet_namespaces.py` documents and regenerates the list: it downloads the three
  `*.Ref` NuGet packages, opens them as ZIP data and reads type names from the XML documentation files
  (`T:Namespace.Type`). It never runs .NET and is never run by tests, like `gen_node_builtins.py`.
- **Rationale**: an exact namespace list (not a `System.*` prefix rule) keeps `using System.Missing;` honest, and
  conditioning ASP.NET and desktop namespaces on the SDK avoids calling them stdlib in a console project.
- **Alternatives**: prefix rule `System.*`/`Microsoft.*` (wrong for `Microsoft.Extensions.*` packages and
  typos); reading an installed SDK (machine-dependent, breaks determinism and FR-016).

## R7. Ecosystems: `dotnet` and `nuget`

- **Decision**: base-library namespaces are `ext:dotnet:<namespace>` (category `stdlib`); packages from
  `PackageReference` are `ext:nuget:<package id>` (category `third_party`); every C# placeholder is
  `unresolved:dotnet:<reference>`. Package ids are matched case-insensitively (NuGet ids are); the node keeps the
  spelling found in the first `.csproj` in path order. The spec was corrected accordingly.
- **Rationale**: `Microsoft.Extensions.Logging` is both a framework namespace (ASP.NET) and a package id; one
  ecosystem would merge two different things into one node with two categories.
- **Alternatives**: `nuget` for both as the issue first suggested (id collisions above); a `dotnet` ecosystem for
  packages too (hides that packages come from NuGet, and future version data belongs to NuGet).

## R8. Edge representation

- **Decision**:
  - `using` edges: type `imports`, form `static`, `type_only` false, `symbol` = the name as resolved
    (namespace for plain using, full type name for static/alias), new fields `directive`
    (`using` | `using_static` | `using_alias`) and `global_using` (bool), both present exactly on C# `imports`
    edges; `alias` = the alias name, allowed on `using_alias` edges in addition to `reexports`.
  - `.csproj` edges: types `project_reference` and `package_reference`, source `project:<path>`, `symbol` = the
    `Include` value as written, form `static`, `type_only` false, line/column/snippet of the item's start tag,
    extractor `csproj-reader@0.1.0`.
  - Confidence/reason rule becomes: `resolved` has no reason; `heuristic` and `unresolved` each require a reason
    from their own list ([contracts/graph.schema.json](contracts/graph.schema.json)).
  - The edge id formula is unchanged (`source|line|column|target|symbol|alias|type`); per-file edges of one
    directive differ by target.
- **Rationale**: keeps the v3 required fields for every edge (no per-language optional provenance), adds only
  what C# needs, and lets the schema enforce the combinations.
- **Alternatives**: overload `form` with C# values (mixes "how the import happens at runtime" with "which
  directive"); a separate edge array for projects (every consumer would need a second code path).

## R9. Schema v4 and its consumers

- **Decision**: bump `SCHEMA_VERSION` to 4 and replace `schema/graph.schema.json` with
  [contracts/graph.schema.json](contracts/graph.schema.json). Consumers updated in the same PR:
  `graph/model.py`, `graph/serialize.py`, `graph/load.py` (project nodes, project-sourced edges, new enums),
  `graph/queries.py` (`resolve()` accepts `.csproj` paths and `dotnet`/`nuget` names; cycles and key files stay
  file-only), `graph/results.py` (names), `store` (validates against the new schema; v3 rows stop being reusable
  through the existing version check), the contract, golden, store-roundtrip and query tests, and every fixture's
  `expected.json` (version only; `.cs` files that were `detected_only` become `analyzed`).
  `006-mcp-server` is not merged; whichever of the two merges second rebases onto the other's schema.
- **Rationale**: constitution VII (one schema, all consumers in one change).
- **Alternatives**: keep v3 and add C# as optional fields (breaks the "schema changes bump the version" rule and
  would let v3 readers silently drop project edges).

## R10. Fixtures

- **Decision**: three new fixtures with hand-written `expected.json` and `queries.json`:
  - `csharp-basic`: one project; block, nested and file-scoped namespaces; a global-namespace type; nested types;
    all definition kinds; plain/static/alias/global usings; `using` inside a namespace block (relative lookup);
    `global::`; base-library namespace; `not_found`; `no_types`; tuple alias with no edge; a syntax error file;
    `#if` block; Razor file; `bin/` and `obj/` with a generated `.cs` file.
  - `csharp-multiproject`: `src/Core`, `src/Web` (Web SDK, ASP.NET namespace), `tests/Core.Tests`;
    `ProjectReference` with `..\` paths, transitive visibility, `not_referenced`, missing project, `$(…)`
    reference, conditional reference; `PackageReference` matched by `package_prefix`, ambiguous prefix, package
    and namespace with the same name in two ecosystems; a `tools/bin/` script folder that is walked.
  - `csharp-edge`: `partial` class over two files (`partial_type`), namespace spread over three files, two
    `.csproj` in one folder (`ambiguous_project`), project-less files, a malformed `.csproj` and one with a
    `DOCTYPE` (both `parse_error`), a mixed Python + C# folder.

  No existing fixture contains `.cs` or `.csproj` files, so existing `expected.json` files change only in
  `schema_version`.
- **Rationale**: spec FR-023; one fixture per concern keeps `expected.json` reviewable by hand.

## R11. Determinism and performance

- **Decision**: all index values are sorted tuples; projects, scopes and directives are processed in path and
  position order; reachability uses sorted adjacency. Resolution caches per (scope, candidate name). The
  performance test generates ~1,000 `.cs` files across 20 projects and asserts < 30 s (marked `slow`), next to
  the existing TS test.
- **Rationale**: constitution II; SC-004, SC-005.
