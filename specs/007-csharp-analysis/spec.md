# Feature Specification: C# Analysis, Slice 1 (Graph Schema v4)

**Feature Branch**: `docs/constitution-csharp` (PR #22, issue #19)

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: "Slice 1 of issue #19 (C# analysis): parse .cs files with a pinned tree-sitter-c-sharp
grammar (namespaces, types, using directives); read .csproj files as data (ProjectReference → project-to-project
edges, PackageReference → NuGet external nodes); resolve each using directive to its namespace and then to the
files that declare types in that namespace; skip bin/ and obj/; .cs files get coverage status analyzed."

## Clarifications

### Session 2026-11-12

- Q: How is a `using` of a namespace declared in several files represented? → A: One edge per declaring file,
  `heuristic` (reason `namespace_spread`) when there are several files and `resolved` when there is one. No
  namespace node.

- During planning (2026-11-12) the spec was corrected: base-library namespaces use ecosystem `dotnet`, apart
  from `nuget` packages, so a namespace and a package with the same name (`Microsoft.Extensions.Logging`) stay
  two nodes; the heuristic package match gets reason `package_prefix`; a `using` inside a namespace block
  follows the compiler's inside-out lookup; aliases to tuple or keyword types create no edge.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See which C# files depend on which (Priority: P1)

A developer runs the existing `graphora analyze <source>` command on a repository with C# code. Every `.cs` file
becomes a file node with its declared types, and every `using` directive becomes an edge with full provenance and
an honest confidence level. Because a `using` names a namespace and not a file, the analysis first builds an
index of which files declare types in which namespace, and then points each `using` at those files.

**Why this priority**: Today `.cs` files are `detected_only`: they appear on the map with no edges. C# is common in
the target repositories, and without edges the map, the queries and the agents see nothing of that code. The
constitution (1.1.0) now allows full analysis for C#.

**Independent Test**: Run the command on the single-project C# fixture and compare the output with its
hand-checked `expected.json`. All expected nodes and edges are present and nothing extra appears.

**Acceptance Scenarios**:

1. **Given** `App/Program.cs` with `using App.Services;` on line 1, and `App/Services/Mailer.cs` and
   `App/Services/Clock.cs` that both declare types in namespace `App.Services`, **When** analyzed, **Then** the
   graph has edges from `App/Program.cs` to both files, at line 1, with the snapshot id, the C# extractor
   name@version and a snippet hash, confidence `heuristic` and reason `namespace_spread` (FR-013).
2. **Given** `using App.Models;` where only `App/Models/User.cs` declares types in `App.Models`, **When**
   analyzed, **Then** there is one `resolved` edge `App/Program.cs → App/Models/User.cs`.
3. **Given** `using System.Collections.Generic;`, **When** analyzed, **Then** there is an edge to a .NET base
   library external node `System.Collections.Generic` with ecosystem `dotnet` and category `stdlib`.
4. **Given** `using Missing.Namespace;` that no file declares, that is not a base-library namespace and that
   matches no package of the project, **When** analyzed, **Then** the edge is `unresolved` with reason
   `not_found`, and no file is guessed.
5. **Given** `using static App.Util.Strings;` where class `App.Util.Strings` is declared in one file, **When**
   analyzed, **Then** there is a `resolved` edge to that file.
6. **Given** `using Json = Newtonsoft.Json.JsonConvert;` in a project with
   `<PackageReference Include="Newtonsoft.Json" />`, **When** analyzed, **Then** there is a `heuristic` edge to the
   NuGet package node `Newtonsoft.Json` (FR-014, FR-013 step 4).
7. **Given** `App/Program.cs` declares `namespace App { class Program { void Main() {} } }`, **When** analyzed,
   **Then** its file node lists the definitions `App.Program` (class) and `App.Program.Main` (method) with
   their lines.

---

### User Story 2 - See how projects reference each other and which packages they use (Priority: P2)

A developer analyzes a solution with several `.csproj` projects. The graph shows each project as a node, which
`.cs` files belong to it, which projects it references and which NuGet packages it uses. Project files are read
as data; `dotnet`, MSBuild and NuGet never run.

**Why this priority**: The project graph is the first thing a .NET developer looks at, and it also defines which
namespaces a file can see (a file sees only its own project and the projects it references). It depends on
nothing but the `.csproj` files, so it is useful on its own.

**Independent Test**: Run on the multi-project fixture and compare with its `expected.json`: project nodes,
project → project edges, project → package edges and the owning project of each `.cs` file.

**Acceptance Scenarios**:

1. **Given** `src/Web/Web.csproj` with `<ProjectReference Include="..\Core\Core.csproj" />` on line 9 and the
   file `src/Core/Core.csproj`, **When** analyzed, **Then** there is a `resolved` project reference edge
   `src/Web/Web.csproj → src/Core/Core.csproj` at line 9 of `src/Web/Web.csproj`.
2. **Given** `<PackageReference Include="Serilog" Version="3.1.1" />`, **When** analyzed, **Then** there is a
   package reference edge from the project to the external node `Serilog` with ecosystem `nuget` and category
   `third_party`.
3. **Given** a `ProjectReference` to a `.csproj` that does not exist in the analyzed folder, **When** analyzed,
   **Then** the edge is `unresolved` with reason `not_found`.
4. **Given** `src/Web/Controllers/Home.cs`, **When** analyzed, **Then** its file node records
   `src/Web/Web.csproj` as its project.
5. **Given** a file in `Web` with `using Core.Domain;` where `Core.Domain` is declared only in the `Core`
   project, and `Web` references `Core`, **When** analyzed, **Then** the edge points to the declaring files in
   `Core`. **Given** the same `using` in a project that does not reference `Core`, **Then** the edge is
   `unresolved` with reason `not_referenced`.

---

### User Story 3 - Build output is skipped and coverage is honest (Priority: P3)

A developer analyzes a repository that has committed or leftover `bin/` and `obj/` folders. They are listed as
skipped, so generated code does not pollute the graph. C# files are reported as `analyzed`, project files as
`not_code`, and Razor files stay `detected_only`.

**Why this priority**: Without the skip rule, generated `*.g.cs` and `AssemblyInfo.cs` files would add false
namespaces to the index. The coverage report is how users learn what was and was not analyzed.

**Independent Test**: The multi-project fixture contains `bin/` and `obj/` folders next to a `.csproj` and a
`bin/` folder with scripts in a non-.NET part of the repository; compare coverage and skipped lists with
`expected.json`.

**Acceptance Scenarios**:

1. **Given** `src/Core/obj/Debug/Core.AssemblyInfo.cs` next to `src/Core/Core.csproj`, **When** analyzed,
   **Then** `src/Core/obj` is skipped with reason `excluded_dir`, and no namespace from it enters the index.
2. **Given** a `tools/bin/` folder with shell and Python scripts and no `.csproj` in `tools/`, **When**
   analyzed, **Then** `tools/bin/` is walked as usual.
3. **Given** `Views/Index.cshtml`, **When** analyzed, **Then** it is `detected_only`.

---

### Edge Cases

- **File-scoped namespace** (`namespace A.B;`) and **block namespaces**, including nested blocks
  (`namespace A { namespace B { … } }` declares `A.B`) and several namespaces in one file: all are indexed.
- **Types in the global namespace** (no namespace declaration): indexed under the global namespace; they are
  visible without a `using` and no `using` can name them.
- **`using A;` where `A` only contains other namespaces** (`A.B`) but no types directly: no file declares types
  in `A`, so there is no file target; the edge is `unresolved` with reason `no_types`.
- **`using` of the file's own namespace**, or a namespace that the file itself also declares: no edge from a file
  to itself.
- **`partial` types** split over several files: each part is a definition in its own file; a `using static` or
  alias that names the type points to all its parts with confidence `heuristic` and reason `partial_type`.
- **Nested types** (`class Outer { class Inner {} }`): definition name `A.Outer.Inner`.
- **`global using`** directives: recorded as edges from the file they are written in, marked global. Applying
  them to the other files of the project is slice 2.
- **The same namespace in a base-library list and declared in the repository**: the repository declaration wins.
- **A namespace that is a segment-prefix of more than one package of the project** (for example packages
  `Foo` and `Foo.Bar` for `using Foo.Bar.Baz;`): `unresolved` with reason `ambiguous`; no package is picked.
- **The same `using` written twice in one file**: one edge per directive.
- **Syntax error in a `.cs` file**: `analyzed` with a `parse_error` flag; definitions and `using` directives from
  readable parts are kept.
- **Preprocessor blocks** (`#if DEBUG … #endif`): not evaluated; directives and types in all branches are
  recorded.
- **`.csproj` that is not well-formed XML**: `not_code` with a `parse_error` flag; it still owns its folder's
  `.cs` files, but contributes no references.
- **`ProjectReference` or `PackageReference` whose path or name contains an MSBuild property** (`$(…)`):
  `unresolved` with reason `msbuild_property`. MSBuild properties are never evaluated.
- **References under a `Condition=` attribute** (on the item or its `ItemGroup`): recorded with confidence
  `heuristic` and reason `msbuild_condition`, because the condition is not evaluated.
- **`PackageReference Update=`** (modifies an existing reference): ignored.
- **A `ProjectReference` to a path outside the analyzed folder**: `unresolved` with reason `not_found`; the
  path is never read.
- **Two `.csproj` files in one folder**: `.cs` files under that folder belong to no project and are listed with
  the coverage flag `ambiguous_project`; they see only project-less files.
- **Nested projects** (a `.csproj` below another project's folder): each `.cs` file belongs to the nearest
  `.csproj` in its folder or a parent folder.
- **`.cs` files with no `.csproj` above them**: project-less. All project-less files form one implicit scope and
  see each other's namespaces.
- **Generated files committed outside `bin/`/`obj/`** (`*.Designer.cs`, `*.g.cs`): analyzed as normal files.
- **Razor, F# and VB.NET** (`.cshtml`, `.razor`, `.fs`, `.vb`): `detected_only`.

## Requirements *(mandatory)*

### Functional Requirements

**Scope and command**

- **FR-001**: The existing `graphora analyze <source>` command MUST analyze C# in addition to Python and
  TypeScript/JavaScript, for local folders, GitHub URLs and ZIP files, with no new flags. All command, safety,
  limit, store and exit-status requirements of features 001–005 apply unchanged.
- **FR-002**: `.cs` files MUST get status `analyzed` and language `csharp`. `.csproj` files MUST be listed with
  language `csharp` and status `not_code`.
- **FR-003**: A folder named `bin` or `obj` MUST be skipped with reason `excluded_dir` when its parent folder
  contains a `.csproj` file. Other `bin` and `obj` folders are walked as before.
- **FR-004**: `.csproj` files MUST be read as XML data only. `dotnet`, MSBuild, NuGet and any task, target or
  import named in them MUST NOT run; MSBuild properties, conditions and `<Import>` elements are not evaluated.

**Extraction from `.cs` files**

- **FR-005**: Each C# file node MUST list its definitions: classes, structs, records, interfaces, enums and
  delegates (top-level and nested) and the methods of those types. Each definition has a kind, a fully qualified
  name (namespace + enclosing types + name) and a 1-based line, sorted as in feature 001.
- **FR-006**: The analysis MUST record every namespace declaration (block, nested block and file-scoped) and the
  namespace that each type is declared in.
- **FR-007**: The analysis MUST record every `using` directive: plain (`using A.B;`), static
  (`using static A.B.C;`), alias (`using X = A.B.C;`) and `global using` of any of these. Each becomes at least
  one edge (FR-013–FR-015) that records which of these forms it is. An alias to a type that names nothing in the
  repository or a library (tuple, array, pointer or built-in keyword type such as `using P = (int, int);`)
  creates no edge.
- **FR-008**: Type references inside method bodies, fields and signatures are NOT extracted in this slice
  (slice 2).

**Extraction from `.csproj` files**

- **FR-009**: Each `.csproj` file MUST become a project node. Each `.cs` file MUST record the project that owns
  it: the nearest `.csproj` in its folder or a parent folder, unless that folder has more than one `.csproj`
  (Edge Cases).
- **FR-010**: Each `<ProjectReference Include="…">` MUST become a project reference edge to the referenced
  project node, resolved against the folder of the `.csproj`, with both `\` and `/` accepted as separators. Each
  `<PackageReference Include="…">` MUST become a package reference edge to an external node with ecosystem
  `nuget` and category `third_party`. Both edges carry full provenance pointing at the line in the `.csproj`.

**Resolution of `using` directives**

- **FR-011**: The analysis MUST build an index from each namespace to the files that declare at least one type
  directly in it, and from each fully qualified type name to the files that declare it (several files for
  `partial` types).
- **FR-012**: A file MUST see only the namespaces declared in its own project and in the projects reachable from
  it through project references (direct and transitive). Project-less files see only project-less files.
- **FR-013**: A plain `using A.B;` MUST be resolved in this order. A `using` written inside a namespace block
  `N` is first tried as `N.A.B`, then with each enclosing namespace of `N` from the inside out, then as `A.B`
  (the compiler's lookup order); the first candidate found in the repository wins. A `global::` prefix skips
  this and means `A.B` only.
  1. `A.B` has declaring files in the visible scope → one edge per declaring file (excluding the file itself):
     `resolved` when there is exactly one, `heuristic` with reason `namespace_spread` when there are several
     (the `using` does not say which of them is used; slice 2 narrows this by type references);
  2. `A.B` is declared in the repository but only outside the visible scope → `unresolved`, reason
     `not_referenced`;
  3. `A.B` is in the .NET base-library namespace list for the file's project → `resolved` edge to a `dotnet`
     external node named `A.B` with category `stdlib`;
  4. `A.B` equals, or starts with followed by `.`, exactly one package id of the file's project → `heuristic`
     edge to that package node with reason `package_prefix` (namespace-to-package naming is a convention, not
     a fact); more than one →
     `unresolved`, reason `ambiguous`;
  5. otherwise → `unresolved`, reason `not_found`.
- **FR-014**: `using static A.B.C;` and an alias whose target is a type MUST point to the files that declare the
  type `A.B.C` in the visible scope: `resolved` for one file, `heuristic` with reason `partial_type` for several.
  If the type is not found, its namespace `A.B` is resolved by steps 2–5 of FR-013.
- **FR-015**: An alias whose target is a namespace MUST resolve exactly like a plain `using` of that namespace.
- **FR-016**: The .NET base-library namespace list MUST be a fixed, versioned data file shipped with the
  extractor and MUST NOT depend on any .NET installation on the machine.
- **FR-017**: Resolution MUST NOT guess: when several candidates remain and no rule above picks one, the edge
  is `unresolved`. Unresolved C# edges point to placeholder nodes in the `dotnet` ecosystem, which never merge
  with Python or npm placeholders.

**Schema v4**

- **FR-018**: The graph format MUST move to schema version 4. `schema/graph.schema.json` MUST allow:
  - file language `csharp`, ecosystems `dotnet` (base library, C# placeholders) and `nuget` (packages);
  - definition kinds `struct`, `record` and `delegate`;
  - a project node kind and the owning project on C# file nodes;
  - edge types for project references and package references, with a project node as source;
  - the record of the `using` form (plain, static, alias, global) on C# edges;
  - reasons `namespace_spread`, `package_prefix`, `not_referenced`, `no_types`, `ambiguous`, `partial_type`, `msbuild_property`, `msbuild_condition`;
  - the coverage flag `ambiguous_project`.
- **FR-019**: Schema v4 MUST keep every provenance rule of v3: an edge without source, target, type, line,
  column, snapshot, confidence, extractor and snippet hash is rejected, and `unresolved` edges carry a reason.
  `heuristic` edges introduced here also carry a reason.
- **FR-020**: Existing fixtures' `expected.json` files MUST be updated by hand to v4. Apart from the version
  number and `.cs` files that move from `detected_only` to `analyzed`, their nodes and edges stay the same.
- **FR-021**: All consumers of the schema in the repository at merge time (store, HTTP API, graph queries,
  frontend types) MUST be updated in the same change (constitution VII). Graph queries treat C# file → file
  edges like other import edges; project-level views are slice 3.

**Determinism and ground truth**

- **FR-022**: All determinism rules of features 001 and 003 MUST hold for C# and mixed repositories:
  byte-identical output for the same snapshot and extractor versions, sorted nodes, edges, index lists and keys.
- **FR-023**: At least two new fixture repositories MUST exist, each with a hand-written `expected.json`.
  Together they MUST cover:
  - block, nested and file-scoped namespaces, a global-namespace type, nested types, a `partial` class over two
    files, and all definition kinds;
  - plain, static, alias and global `using`, a base-library namespace, a namespace with no types, and a
    namespace that is not found;
  - two or more projects with a `ProjectReference`, a namespace that is declared but not referenced, a
    `PackageReference` matched by a `using`, and an ambiguous package prefix;
  - a `Condition=` reference and a `$(…)` reference;
  - a `.cs` file with a syntax error and a malformed `.csproj`;
  - `bin/` and `obj/` next to a `.csproj`, and a `bin/` folder elsewhere that is walked;
  - a Razor file that stays `detected_only`.
- **FR-024**: Automated tests MUST compare each fixture's output with its `expected.json`, check that repeated
  runs give identical bytes, and validate the output against schema v4.

### Key Entities

- **C# file node**: an analyzed `.cs` file with its definitions and owning project.
- **Definition**: a class, struct, record, interface, enum, delegate or method, with its fully qualified name and
  line.
- **Project node**: a `.csproj` file; owns `.cs` files, references other projects and packages.
- **Namespace index**: namespace → declaring files, and type → declaring files, scoped by project visibility.
  Used for resolution; not itself part of the graph output.
- **External node**: a base-library namespace (ecosystem `dotnet`, category `stdlib`) or a referenced NuGet
  package (ecosystem `nuget`, category `third_party`).
- **Using edge**: one `using` directive from a file node to a target, with its form, provenance and confidence.
- **Project reference / package reference edge**: one `<ProjectReference>` or `<PackageReference>` item, from a
  project node, with provenance in the `.csproj`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On every C# fixture, 100% of the hand-checked nodes and edges are reproduced, and no unexpected node
  or edge appears.
- **SC-002**: Zero guesses: every `using` and project item in the fixtures that the documented rules cannot settle
  to one target is reported as `unresolved` or `heuristic` with a reason, never as a single wrong target.
- **SC-003**: All existing Python, TS/JS and mixed fixtures still pass after the move to schema v4, with no change
  beyond FR-020.
- **SC-004**: 10 consecutive runs on each new fixture, from two different absolute paths, produce byte-identical
  output.
- **SC-005**: A repository with about 1,000 `.cs` files across 20 projects is analyzed in under 30 seconds on a
  typical developer laptop.
- **SC-006**: 100% of files in each C# fixture are accounted for in the coverage report, either as an entry or
  under a skipped folder.
- **SC-007**: No process other than the analyzer itself is started during analysis of a C# repository.

## Assumptions

- Slices 2 and 3 of issue #19 follow in the same branch and PR: type-level resolution, global usings applied
  across a project, `ImplicitUsings`, `<Using>` items, nested-namespace lookup, `Directory.Build.props` (slice 2);
  `.sln` files, project views in the queries, API and frontend (slice 3).
- `.cs` files belong to a project by folder (the SDK-style default `**/*.cs`). Explicit `<Compile Include/Remove>`
  items, old-style (non-SDK) project files that list every file, and `Directory.Packages.props` (central package
  versions) are not interpreted in this slice; package ids are taken from `PackageReference` only.
- Package versions are not stored; packages are identified by id, as for npm.
- `bin` and `obj` are skipped only next to a `.csproj`, because Python and shell repositories often have a `bin/`
  folder with real scripts.
- The `tree-sitter-c-sharp` grammar version is pinned exactly, as for the other grammars (issue #8).
- No language model is involved; MCP and agent behaviour is unchanged apart from seeing the new edges.
