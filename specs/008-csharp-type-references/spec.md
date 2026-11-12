# Feature Specification: C# Analysis, Slice 2 — Type References and Project-wide Usings

**Feature Branch**: `docs/constitution-csharp` (PR #22, issue #19)

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: "slice 2 of issue 19" — type-level resolution (file → file by the types a file actually
uses), global and implicit usings across a project, `<Using>` items, aliases in code, nested-namespace lookup and
`Directory.Build.props`, on top of slice 1 ([specs/007-csharp-analysis](../007-csharp-analysis/spec.md)).

## Clarifications

### Session 2026-11-12

- Q: What happens to the slice-1 `using` edges to repository files once type references are found? → A: Type
  references become the file → file edges. A `using` keeps its edges to repository files only when no type from
  its namespace (or its alias) is referenced in the file; those fallback edges keep their slice-1 confidence
  (`heuristic` when the namespace spans several files). Edges from a
  `using` to base-library namespaces, packages and placeholders are unchanged.

- During planning (2026-11-12) SC-002 was corrected: it is measured on the slice-2 fixture, because
  `csharp-basic` writes almost no types and its edges barely change.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dependencies point at the file that is really used (Priority: P1)

A developer analyzes a C# repository and asks which files depend on `Mailer.cs`. Today every file that writes
`using App.Services;` is listed as a "likely" dependent of every file in that namespace. After this slice, a file
is linked to `Mailer.cs` because it writes `Mailer` (a field type, `new Mailer()`, a base type…), at the line where
it first does so, and the link is a fact, not a guess.

**Why this priority**: Slice 1 links whole namespaces, so in a real project (namespaces with dozens of files)
dependents, impact and cycles are mostly noise. Type references are what makes the C# graph trustworthy.

**Independent Test**: Run on the slice-2 fixture and compare with its hand-written `expected.json`: each file →
file edge matches a type the file writes, at the first line it is written, with no extra edges.

**Acceptance Scenarios**:

1. **Given** `Program.cs` with `using App.Services;` on line 1 and `var m = new Mailer();` on line 9, and
   `App.Services` declared in `Mailer.cs`, `Clock.cs` and `Queue.cs`, **When** analyzed, **Then** there is one
   `resolved` edge `Program.cs → Mailer.cs` at line 9, and no edge to `Clock.cs` or `Queue.cs`.
2. **Given** a file that uses `Mailer` on lines 9, 14 and 20, **When** analyzed, **Then** there is exactly one edge
   to `Mailer.cs`, at line 9.
3. **Given** `Clock.cs` and `Mailer.cs` both in namespace `App.Services`, and `Mailer.cs` has a field `Clock clock;`
   with no `using`, **When** analyzed, **Then** there is an edge `Mailer.cs → Clock.cs` (same namespace).
4. **Given** code in namespace `App.Web.Controllers` that uses `Settings` declared in namespace `App`, without a
   `using`, **When** analyzed, **Then** there is an edge to the file declaring `App.Settings` (enclosing
   namespaces are visible).
5. **Given** a file with `using App.Extensions;` where no type of `App.Extensions` is written (only extension
   methods are called), **When** analyzed, **Then** the slice-1 edges from that `using` remain, with their slice-1
   confidence.
6. **Given** `Timer` declared in two namespaces that the file both imports, **When** analyzed, **Then** the
   reference is `unresolved` with reason `ambiguous`, and no file is picked.
7. **Given** a reference to a `partial` class split over two files, **When** analyzed, **Then** there are edges to
   both parts, `heuristic`, reason `partial_type`.
8. **Given** a fully qualified reference `App.Models.User u;` with no `using`, **When** analyzed, **Then** there
   is an edge to the file declaring `App.Models.User`.

---

### User Story 2 - Project-wide usings are understood (Priority: P2)

A developer analyzes a modern .NET project where most files have no `using` lines: the namespaces come from
`global using` files, from `<ImplicitUsings>enable</ImplicitUsings>` and from `<Using Include="…" />` items in the
project file or in `Directory.Build.props`. Type references in those files are still resolved correctly.

**Why this priority**: .NET 6+ templates enable implicit usings by default, and `GlobalUsings.cs` is common.
Without this, type references in most modern files would look up only their own namespace and miss everything.

**Independent Test**: Run on a fixture with a `GlobalUsings.cs`, `ImplicitUsings` and a `Directory.Build.props`;
compare with `expected.json`.

**Acceptance Scenarios**:

1. **Given** `GlobalUsings.cs` with `global using App.Models;` and another file of the same project that writes
   `User` with no `using`, **When** analyzed, **Then** there is an edge from that file to `User.cs`.
2. **Given** `<ImplicitUsings>enable</ImplicitUsings>` and a file that writes `List<int>` and `Task` with no
   `using`, **When** analyzed, **Then** those names are recognized as base-library types (no edge to a repository
   file, no `unresolved` entry).
3. **Given** `<Using Include="App.Shared" />` in the project file, **When** a file writes a type of `App.Shared`,
   **Then** the edge is created as if the file had `using App.Shared;`.
4. **Given** `Directory.Build.props` in a parent folder that enables `ImplicitUsings` and adds a `<Using>` item,
   **When** analyzed, **Then** both apply to every project below that folder.
5. **Given** a `<Using>` item or `ImplicitUsings` value that sits under a `Condition` or uses `$(…)`, **When** a
   resolution depends on it, **Then** the resulting edge is `heuristic` with reason `msbuild_condition`.

---

### User Story 3 - Aliases and static usings in code (Priority: P3)

A developer uses `using U = App.Models.User;` and writes `U` in code, or `using static App.Util.Strings;` and
calls `Upper(...)`. References through an alias count as references to the aliased type.

**Why this priority**: Aliases are less common than plain usings, but without them alias users would fall back to
heuristic edges.

**Independent Test**: Fixture cases for alias and static usings compare with `expected.json`.

**Acceptance Scenarios**:

1. **Given** `using U = App.Models.User;` and `U.Create()` on line 7, **When** analyzed, **Then** the edge to
   `User.cs` is at line 7 (the first use), and the alias directive keeps no separate fallback edge.
2. **Given** `using static App.Util.Strings;` and an unqualified call `Upper(x)`, **When** analyzed, **Then** the
   slice-1 `resolved` edge from the directive to `Strings.cs` stays (members are not matched by name).

---

### Edge Cases

- **Name that matches nothing in the repository or the base library** (usually a package type): no edge and no
  `unresolved` entry; it is counted in the file's coverage as unresolved type names (FR-012).
- **Name declared in the repository and also a base-library type in an imported namespace** (`Task`): `unresolved`,
  reason `ambiguous`, as the compiler would also refuse it.
- **Same short name in the file's own namespace and an imported one**: the enclosing namespace wins (compiler
  rule), so this is not ambiguous.
- **Generic types** (`Repository<User>`, `Dictionary<string, Order>`): the generic type and every type argument
  are references. A name with generic arity (`Box<T>`) matches the declared `Box` type.
- **Nested types** (`Outer.Inner`): matched to the file declaring `Outer`; partial outer types → all parts.
- **References inside the type's own file**: no self-edge.
- **Type parameters** (`T` in `class Box<T>`) and local variables are not type references.
- **`var`, lambdas, LINQ and other inferred types**: invisible; they produce no edge (counted as missed in the
  benchmark, never guessed).
- **Attributes** (`[Serializable]`, `[MyCheck]`): `MyCheck` also tries `MyCheckAttribute`, as the compiler does.
- **`typeof(T)`, `nameof(T)`, `is T`, `as T`, casts, `catch (T e)`, `T.StaticMember`**: references.
- **Fully qualified and `global::` names** in code: looked up directly, no relative lookup for `global::`.
- **Preprocessor blocks**: references in every branch are recorded.
- **Files with syntax errors**: references in readable parts are kept.
- **A `global using` in one project**: never applies to another project.
- **`Directory.Build.props` above the analyzed root**: not read. Several nested ones: the nearest applies, and an
  `<Import>` of a parent one is not followed (only the nearest file is read).
- **A `using` alias that is never used in code**: keeps its slice-1 edge (fallback).
- **Razor, generated code from source generators**: out of scope; their types are not visible.

## Requirements *(mandatory)*

### Functional Requirements

**Type references**

- **FR-001**: The analysis MUST extract the type names a `.cs` file writes: base types and interfaces, field,
  property, event, parameter, return and local variable types, `new T(...)`, generic type arguments, array and
  nullable element types, attributes, `typeof`, `nameof`, `is`/`as`/casts, `catch` types, and the qualifier of
  static member access (`T.Member`) when `T` is not a local name.
- **FR-002**: Each type name MUST be resolved with the compiler's lookup order: the enclosing namespaces of the
  reference from the inside out, then the file's using aliases, then the namespaces imported by the file's own
  `using` directives, then the project's global usings (FR-006–FR-008); a fully qualified name is looked up
  directly. The first level that has a match wins; two or more matches at the same level is `ambiguous`.
- **FR-003**: A reference resolved to one repository type declared in one file MUST give a `resolved` edge to that
  file. A `partial` type gives `heuristic` edges with reason `partial_type` to every part.
- **FR-004**: There MUST be at most one type-reference edge per (source file, target file), at the first line and
  column where any type of the target file is referenced. No self-edges.
- **FR-005**: Type-reference edges MUST carry full provenance (line, column, snapshot, extractor, snippet hash of the
  referencing line) and be distinguishable from `using` directive edges.

**Project-wide usings**

- **FR-006**: `global using` directives MUST apply to every `.cs` file of the same project (or, for project-less
  files, to the project-less group).
- **FR-007**: `<ImplicitUsings>enable</ImplicitUsings>` (or `true`) MUST add the implicit global usings of the
  project's SDK, from a fixed versioned list shipped with the extractor (`Microsoft.NET.Sdk`, `.Web`, `.Worker`,
  `.Razor`, `.BlazorWebAssembly`, `.WindowsDesktop`).
- **FR-008**: `<Using Include="X" />` items MUST add `X` as a global using; `<Using Include="X" Alias="Y" />` a global
  alias; `<Using Include="X" Static="true" />` a global static using; `<Using Remove="X" />` removes one.
- **FR-009**: `Directory.Build.props` files inside the analyzed folder MUST be read as data: the nearest one in
  the project's folder or above applies to that project. Only `ImplicitUsings`, `<Using>` items and
  `PackageReference` items are taken from it; `<Import>` and `$(…)` are never followed or expanded.
- **FR-010**: A resolution that depends on a value under a `Condition` (in the project file or
  `Directory.Build.props`) MUST be `heuristic` with reason `msbuild_condition`; one that depends on a `$(…)`
  value MUST treat that value as absent.

**Using fallback and externals**

- **FR-011**: A `using` directive's slice-1 edges to repository files MUST be kept only when the file references no
  type through that directive (no resolved name from its namespace, alias or static type). Its edges to
  base-library namespaces, packages and placeholders MUST stay as in slice 1.
- **FR-012**: The base-library type names MUST come from a fixed versioned list shipped with the extractor (the
  slice-1 namespace list extended with type names). A name matching only a base-library type gives no edge. A name
  matching nothing gives no edge; each file's coverage entry MUST report how many distinct type names stayed
  unresolved, so missing information is visible.
- **FR-013**: Resolution MUST NOT guess: ambiguity is `unresolved: ambiguous`; type inference, overload resolution
  and extension-method binding are not attempted.

**Schema, determinism, ground truth**

- **FR-014**: The graph format MUST move to schema version 5 with the type-reference edge kind, the coverage count
  from FR-012 and any new reason values; every consumer in the repository (serializer, loader, queries, store,
  MCP server, tests, fixtures) MUST change in the same PR (constitution VII).
- **FR-015**: Determinism rules of features 001, 003 and 007 MUST hold: byte-identical output, sorted everything.
- **FR-016**: At least one new fixture repository with a hand-written `expected.json` MUST cover: same-namespace
  and enclosing-namespace references, every reference position from FR-001, a namespace used through one type
  only, an extension-method-only `using` (fallback), ambiguity with a repository type and with a base-library type,
  `partial` and nested types, generics, attributes with and without the `Attribute` suffix, `global using`,
  `ImplicitUsings` for two SDKs, `<Using>` items with alias, static and `Remove`, a `Directory.Build.props` that
  applies to two projects, a conditional `<Using>`, a used and an unused alias. The three slice-1 fixtures MUST be
  updated by hand for the new edges.

### Key Entities

- **Type reference**: one type name written in a file, with its position and enclosing namespace.
- **Type-reference edge**: the first reference from one file to a type declared in another file.
- **Project usings**: the global usings, aliases and static usings that apply to every file of one project, with
  where each came from (`global using`, implicit list, `<Using>` item, `Directory.Build.props`) and whether it is
  conditional.
- **Base-library type list**: shipped list of type names per base-library namespace and framework.
- **Implicit usings list**: shipped list of implicit global usings per SDK.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On every C# fixture, 100% of hand-checked nodes and edges are reproduced, and no unexpected node or
  edge appears.
- **SC-002**: On the slice-2 fixture, every file → file dependency that the code shows through a written type is a
  `resolved` (or `partial_type`) type-reference edge, and `heuristic` `using` edges to repository files remain only
  for directives through which no type is referenced.
- **SC-003**: Zero guesses: every type name the documented rules cannot settle to one declaring type is
  `unresolved`, a `partial_type` edge, a fallback `heuristic` edge, or counted as unresolved — never a single wrong
  file.
- **SC-004**: 10 runs on each C# fixture, from two absolute paths, give byte-identical output.
- **SC-005**: A repository with about 1,000 `.cs` files across 20 projects is still analyzed in under 30 seconds.
- **SC-006**: All Python, TS/JS and mixed fixtures pass unchanged apart from the schema version.

## Assumptions

- Slice 1 (feature 007) is merged into this branch and stays the base: ownership, visibility through project
  references, base-library and package handling are reused as they are.
- Extension methods, `var`, LINQ and overloads stay out of scope (no type inference); the `using` fallback keeps
  their dependencies visible as `heuristic`.
- The base-library type list and implicit-usings list are generated from the official .NET 10 reference packs and
  SDK data, like the slice-1 namespace list; no .NET SDK is needed to analyze.
- Package types cannot be listed without downloading packages, so references to them give no edge; the package
  dependency stays visible through the `using` → package edge from slice 1.
- `Directory.Packages.props` (central package versions) adds no information the graph needs (versions are not
  stored).
- `.sln` files, project-level views in queries, API and UI are slice 3.
