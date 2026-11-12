---

description: "Task list for 007-csharp-analysis (slice 1 of issue #19)"
---

# Tasks: C# Analysis, Slice 1 (Graph Schema v4)

**Input**: Design documents from `specs/007-csharp-analysis/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/graph.schema.json, contracts/cli.md,
quickstart.md

**Tests**: Required. FR-023, FR-024 and constitution Principle VIII require golden, determinism and schema
tests. Each task ships its own tests: write them first, confirm they fail, then implement.

**Commits**: one commit per task, pushed right after it, on branch `docs/constitution-csharp` (PR #22). Every
task leaves `uv run pytest -m "not slow and not db"` green.

**Organization**: tasks are grouped by user story:

- US1 (P1): C# file → file edges from `using` directives, inside one project;
- US2 (P2): projects, project and package references, visibility across projects;
- US3 (P3): `bin`/`obj` skip rule and honest coverage.

Schema v4 and the query-layer changes are foundational: nothing can emit C# nodes before the schema allows
them, and existing golden tests must stay green from the first commit.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1, US2, US3)

Paths are relative to the repository root. Python code lives in `backend/src/graphora/`, tests in
`backend/tests/`, fixtures in `fixtures/repos/`. Run commands from `backend/`.

---

## Phase 1: Setup

**Purpose**: the pinned grammar and the shipped base-library namespace list.

- [X] T001 Add `tree-sitter-c-sharp==0.23.5` to `dependencies` in `backend/pyproject.toml`, keeping all other
  exact pins; run `uv sync` and commit `backend/uv.lock`. Check in a test that
  `tree_sitter.Language(tree_sitter_c_sharp.language())` loads with `tree-sitter==0.25.2` (ABI 15) in
  `backend/tests/unit/test_cs_extract.py` (new file, one test for now).
- [X] T002 [P] Create `backend/scripts/gen_dotnet_namespaces.py` and generate
  `backend/src/graphora/resolve/data/dotnet_namespaces.txt` (research R6):
  - the script downloads `Microsoft.NETCore.App.Ref`, `Microsoft.AspNetCore.App.Ref` and
    `Microsoft.WindowsDesktop.App.Ref` version `10.0.0` from `https://api.nuget.org/v3-flatcontainer/`, opens each
    `.nupkg` as ZIP data in memory, reads every `ref/net10.0/*.xml` documentation file with expat (DTDs refused),
    and collects the namespace of every `T:` member (text before the last `.` of the type name, nested `+`
    types reduced to their outer type, generic arity `` `N `` dropped);
  - output: first line `# dotnet-namespaces@10.0.0`, then one `<framework> <namespace>` pair per line, framework
    one of `Microsoft.NETCore.App`, `Microsoft.AspNetCore.App`, `Microsoft.WindowsDesktop.App`, sorted, unique,
    UTF-8, LF;
  - module docstring: needs network, never runs .NET, never run by tests or `analyze`, reads nothing from
    analyzed repositories.

---

## Phase 2: Foundational (schema v4 and the query layer)

**Purpose**: after this phase every existing fixture passes on schema v4 and the queries understand project
and C# external ids, before any C# code exists.

- [ ] T003 Move the graph format to schema v4 in one change (research R8, R9; data-model.md):
  - copy `specs/007-csharp-analysis/contracts/graph.schema.json` to `schema/graph.schema.json`;
  - `backend/src/graphora/graph/model.py`: `Ecosystem` adds `"dotnet"`, `"nuget"`; `DefinitionKind` adds
    `"struct"`, `"record"`, `"delegate"`; `EdgeType` adds `"project_reference"`, `"package_reference"`; `Reason`
    adds `"not_referenced"`, `"no_types"`, `"ambiguous"`, `"msbuild_property"`, `"namespace_spread"`,
    `"partial_type"`, `"package_prefix"`, `"msbuild_condition"`; `Flag` adds `"ambiguous_project"`; new frozen
    `ProjectNode(path)` with `id = f"project:{path}"`; `FileNode.project: str | None = None`; `Edge` gains
    `directive: Literal["using", "using_static", "using_alias"] | None = None` and `global_using: bool | None =
    None`. `Edge.__post_init__` enforces: "`resolved` → no `reason`; `heuristic` and `unresolved` each require a
    reason from their own list"; `directive` and `global_using` are both set or both `None`; `alias` only on
    `reexports` or `directive == "using_alias"`, and always on `using_alias`;
  - `backend/src/graphora/graph/serialize.py`: `SCHEMA_VERSION = 4`; project nodes as
    `{"id", "kind": "project", "path"}`; C# file nodes write `project` (may be `null`) and no `exports`; edges
    write `directive` and `global_using` only when set; edge id formula unchanged;
  - `backend/src/graphora/graph/load.py`: `_LANGUAGES` adds `"csharp"`; reads project nodes, `project`,
    `directive`, `global_using`; `_check_edges` requires a file-node source for `imports`/`reexports` and a
    project-node source for `project_reference`/`package_reference`;
  - set `"schema_version": 4` in every `fixtures/repos/*/expected.json` (by hand; no other change) and in any
    test document that states 3;
  - tests: v4 accept/reject samples in `backend/tests/contract/test_schema.py` (the 21 samples listed in
    plan.md § Constitution Check, plus `test_old_schema_version_rejected` for 3), model rules in
    `backend/tests/unit/test_serialize.py`, loader cases in `backend/tests/unit/test_load.py`; projection in
    `backend/tests/conftest.py` gains `project`, `directive`, `global_using`.
- [ ] T004 Teach the query layer about project and C# ids (contracts/cli.md § Query commands):
  - `backend/src/graphora/graph/queries.py` `resolve()`: a path ending in `.csproj` maps to `project:<path>`
    when that node exists; external names are tried as `ext:npm:`, `ext:python:`, `ext:nuget:`, `ext:dotnet:`,
    more than one match raises the existing `ambiguous` `NodeNotFound`; `cycles` and `key_files` stay file-only;
  - `backend/src/graphora/graph/results.py` `_name()`: `project:src/A/A.csproj` → `src/A/A.csproj`,
    `ext:nuget:Serilog` → `nuget:Serilog`, `ext:dotnet:System.Linq` → `dotnet:System.Linq`;
  - tests on a hand-built v4 document in `backend/tests/unit/test_index.py` and
    `backend/tests/unit/test_neighbors.py` (project node dependencies, heuristic "(likely)" mark, ambiguous
    `nuget`/`npm` name).

**Checkpoint**: full suite green on v4; no C# output yet.

---

## Phase 3: User Story 1 - See which C# files depend on which (Priority: P1) 🎯 MVP

**Goal**: `.cs` files are analyzed; `using` directives become file → file, `dotnet` and placeholder edges inside
one project (or among project-less files).

**Independent Test**: `uv run pytest tests/golden -k csharp-basic` matches the hand-written `expected.json`.

- [ ] T005 [P] [US1] Implement the C# extractor in `backend/src/graphora/adapters/csharp/__init__.py`
  (`VERSION = "0.1.0"`, `EXTRACTOR = "csharp-adapter@0.1.0"`) and
  `backend/src/graphora/adapters/csharp/extract.py` (research R1, data-model.md § Internal entities):
  - `extract(data: bytes, check) -> CsFacts | None`; decode with the shared text helper (BOM, UTF-8);
  - namespaces from `namespace_declaration` (nested blocks join names: `A { B.C {} }` → `A.B.C`) and
    `file_scoped_namespace_declaration`; global namespace is `""`;
  - definitions for `class`, `struct`, `record` (incl. `record struct`), `interface`, `enum`, `delegate`
    declarations at any nesting and `method_declaration` inside them; name "fully qualified: namespace + enclosing
    types + name, `.`-joined, generic parameters dropped"; line of the name node; record `partial` modifier;
  - using directives with form (`global`/`static` tokens, `name` field = alias), target text with `global::`
    removed and a `global_qualified` flag, generic arguments removed, or `kind="non_name"` for `tuple_type`,
    `array_type`, `pointer_type`, `predefined_type`, `nullable_type`; enclosing namespace (`""` at file level);
    line, column (via `adapters/position.py`), directive text;
  - directives and types inside `preproc_if`/`preproc_else` are kept; `has_error` from the tree;
  - tests in `backend/tests/unit/test_cs_extract.py`: each form, nested and file-scoped namespaces, nested types,
    every kind, partial, `#if`, a syntax error keeping readable parts, column on a line with a tab and non-ASCII.
- [ ] T006 [P] [US1] Implement single-scope resolution in `backend/src/graphora/resolve/csharp.py`
  (`RESOLVER_VERSION = "0.1.0"`, `NAMESPACES_VERSION = "10.0.0"`, research R4–R6, data-model.md § Resolution):
  - load `dotnet_namespaces.txt` into `framework → frozenset(namespaces)`;
  - `owner(path, csproj_paths) -> (project | None, ambiguous: bool)`: first folder upwards holding `.csproj`
    files; one → owner, two or more → `None` + ambiguous;
  - `Scope` index: namespace → sorted declaring files (types declared directly in it), full type name → sorted
    declaring files; "declared as parent only" set; one scope per project and one for project-less files;
  - `resolve_using(path, directive, visible_scopes, frameworks, packages) -> list[Target]` with candidates
    `A.B.X`, `A.X`, `X` (only `X` at file level, for `global using`, or with `global::`), steps of FR-013/014/015,
    no self-edges, `no_types`, `non_name` aliases → no target, reason priority `partial_type`,
    `namespace_spread`, `package_prefix`, `msbuild_condition`; in this task `visible_scopes` is just the file's
    own scope and `frameworks` is `{"Microsoft.NETCore.App"}`;
  - tests in `backend/tests/unit/test_cs_resolve.py` covering every row of the `using` table that does not need
    project references or packages.
- [ ] T007 [US1] Wire C# into the build (depends on T005, T006):
  - `backend/src/graphora/detect/languages.py`: `.cs` → `csharp` analyzed (removed from detected-only);
    `.csproj` (by extension), `.sln`, `Directory.Build.props`, `Directory.Packages.props` → `csharp` `not_code`;
    `.cshtml`/`.razor` → `razor`, `.fs` → `fsharp`, `.vb` → `vb` detected-only;
  - `backend/src/graphora/graph/build.py`: a `_csharp_graph` pass after `_js_graph`: file nodes with
    `project` (owner or `None`), `ambiguous_project` coverage flag, `using` edges with
    `extractor=csharp.EXTRACTOR`, `form="static"`, `type_only=False`, `directive`, `global_using`, `symbol`,
    `alias`, snippet hash of the directive text; `dotnet` external nodes (`stdlib`) and `dotnet` placeholders;
    `current_extractors()` adds `csharp-adapter`, `csharp-resolver`, `dotnet-namespaces`;
  - `backend/tests/unit/test_extractor_versions.py` + `extractor_versions.json`: components `csharp-adapter`
    (`adapters/csharp/*.py`, `adapters/position.py`, grammar pins), `csharp-resolver` (`resolve/csharp.py`),
    `dotnet-namespaces` (`resolve/data/dotnet_namespaces.txt`);
  - tests: `backend/tests/unit/test_languages.py`, `backend/tests/unit/test_build_analyze.py` (a two-file C#
    folder end to end, schema-valid).
- [ ] T008 [US1] Add fixture `fixtures/repos/csharp-basic/` with `repo/`, hand-written `expected.json` and
  `queries.json` (research R10): one `App/App.csproj`; block, nested and file-scoped namespaces; a
  global-namespace type; nested types; every definition kind; a `partial` class over two files; plain, static,
  alias, namespace-alias and `global using`; a `using` inside a namespace block resolved by relative lookup;
  `global::System.IO`; `System.Collections.Generic`; a namespace spread over three files; `no_types`;
  `not_found`; a tuple alias with no edge; a `#if DEBUG` using; a file with a syntax error; a `.cshtml` file.
  `queries.json`: `dependents` of a file in the spread namespace and `dependencies` of `Program.cs`. The golden,
  determinism and query tests pick the fixture up automatically.

**Checkpoint**: US1 works on its own; `csharp-basic` passes golden, determinism and query tests.

---

## Phase 4: User Story 2 - Projects, references and packages (Priority: P2)

**Goal**: project nodes, `project_reference` and `package_reference` edges, owning project on files, visibility
across referenced projects, packages and SDK-dependent frameworks in `using` resolution.

**Independent Test**: `uv run pytest tests/golden -k "csharp-multiproject or csharp-edge"` matches the
hand-written `expected.json` files.

- [ ] T009 [P] [US2] Implement the `.csproj` reader in `backend/src/graphora/adapters/msbuild/__init__.py`
  (`VERSION = "0.1.0"`, `EXTRACTOR = "csproj-reader@0.1.0"`) and `backend/src/graphora/adapters/msbuild/csproj.py`
  (research R2):
  - `read(data: bytes) -> ProjectFacts` with expat; `StartDoctypeDeclHandler` raises → `has_error=True` and no
    items; malformed XML → `has_error=True` and no items;
  - element local names (prefix and the MSBuild 2003 namespace ignored); root `Project` `Sdk`; `UseWPF`,
    `UseWindowsForms` property text equal to `true` (case-insensitive, trimmed);
  - items `ProjectReference`, `PackageReference`, `FrameworkReference` with `Include` only (`Update`, `Remove`
    ignored), split on `;`, empty entries dropped; `conditional` when the item or its `ItemGroup` has
    `Condition`; 1-based line, column via `adapters/position.py`, start-tag text for the snippet hash;
  - never follows `<Import>`, never reads another file;
  - tests in `backend/tests/unit/test_csproj.py`: each item kind, `;` lists, conditions on item and group,
    `Update`, namespace-qualified old-style project, BOM, DOCTYPE with an entity, truncated XML, positions.
- [ ] T010 [US2] Extend `backend/src/graphora/resolve/csharp.py` with projects (depends on T006, T009):
  - `ProjectReference`: `$(`, `@(`, `*`, `?` → `unresolved: msbuild_property`; `\` → `/`, join to the
    `.csproj` folder, normalize; leaving the root or not a walked `.csproj` → `unresolved: not_found` (reference
    = tried path, or `Include` text when outside the root); else `resolved`, or `heuristic: msbuild_condition`
    when conditional;
  - `PackageReference`: `$(` → `unresolved: msbuild_property`; else `ext:nuget:<id>` `resolved` or
    `heuristic: msbuild_condition`; ids compared case-insensitively, node spelling from the first `.csproj` in
    path order;
  - visibility: per project, reachable scopes through unconditional references and through all references
    (transitive, sorted); a target only reachable through a conditional reference → `heuristic:
    msbuild_condition`; `not_referenced` when declared only outside visible scopes;
  - frameworks per project: `Microsoft.NETCore.App` always; `Microsoft.AspNetCore.App` for `Sdk` in
    {`Microsoft.NET.Sdk.Web`, `Microsoft.NET.Sdk.Razor`, `Microsoft.NET.Sdk.BlazorWebAssembly`} or a
    `FrameworkReference` to it; `Microsoft.WindowsDesktop.App` for `UseWPF`/`UseWindowsForms`;
  - packages per project for FR-013 step 4: exactly one id equal to or a `.`-prefix of the namespace
    (case-insensitive) → `heuristic: package_prefix`; several → `unresolved: ambiguous`;
  - tests in `backend/tests/unit/test_cs_resolve.py` for every remaining row of the data-model tables.
- [ ] T011 [US2] Wire projects into the build and CLI (depends on T010):
  - `backend/src/graphora/graph/build.py`: read every walked `.csproj`; project nodes (also for `parse_error`
    ones); `project_reference`/`package_reference` edges with `extractor="csproj-reader@0.1.0"`, `symbol` = the
    `Include` entry as written, `form="static"`, `type_only=False`; `nuget` external nodes; `parse_error`
    coverage flag on broken `.csproj` files and their paths added to the warnings; `current_extractors()` adds
    `csproj-reader`; `extractor_versions.json` entry for `adapters/msbuild/*.py`;
  - `backend/src/graphora/cli/__init__.py`: warning text by file type: `.csproj` →
    `ignoring <path>: not well-formed XML or has a DOCTYPE`, others unchanged;
  - tests: `backend/tests/unit/test_build_analyze.py` (two projects end to end),
    `backend/tests/integration/test_cli.py` (warning line, exit status 0).
- [ ] T012 [US2] Add fixture `fixtures/repos/csharp-multiproject/` with `repo/`, hand-written `expected.json` and
  `queries.json` (research R10): `src/Core/Core.csproj`, `src/Web/Web.csproj` (`Microsoft.NET.Sdk.Web`),
  `tests/Core.Tests/Core.Tests.csproj`; `..\` project references incl. a transitive one, a missing project, a
  `$(…)` reference, a conditional reference; `Serilog` package matched by `package_prefix`, packages `Foo` and
  `Foo.Bar` for an `ambiguous` namespace, `Microsoft.Extensions.Logging` as package and ASP.NET namespace in two
  ecosystems; a `using` of a namespace only declared in an unreferenced project (`not_referenced`);
  `using Microsoft.AspNetCore.Mvc;` in Web (`dotnet`, stdlib) and in Core (`not_found`). `queries.json`:
  `dependencies` of `src/Web/Web.csproj`, `dependents` of a Core file.
- [ ] T013 [US2] Add fixture `fixtures/repos/csharp-edge/` with `repo/`, hand-written `expected.json` and
  `queries.json`: two `.csproj` in one folder (`ambiguous_project`, `project: null`), project-less files that see
  each other, a malformed `.csproj` and one with a `DOCTYPE` and an entity (both `parse_error`, still owning their
  files), a `<Import Project="evil.targets" />` that is never read, and a Python file next to the C# code.

**Checkpoint**: US1 and US2 pass golden, determinism and query tests.

---

## Phase 5: User Story 3 - Build output is skipped and coverage is honest (Priority: P3)

**Goal**: `bin`/`obj` next to a `.csproj` are skipped; other `bin` folders are walked.

**Independent Test**: `uv run pytest tests/unit/test_walk.py tests/golden -k csharp` with the new folders in the
fixtures.

- [ ] T014 [US3] Implement the `bin`/`obj` rule in `backend/src/graphora/ingest/walk.py` (research R3): while
  listing a folder, if any entry is a regular file whose name ends in `.csproj` (case-insensitive), sub-folders
  named `bin` or `obj` are added to `skipped` with reason `excluded_dir` and not descended; `EXCLUDED_DIRS`,
  `is_excluded_path`, `ingest/archive.py` and `ingest/snapshot.py` stay unchanged. Add to the fixtures:
  `csharp-basic/repo/App/bin/Debug/App.dll` and `App/obj/Debug/App.AssemblyInfo.cs` (declares a namespace that
  must not enter the index); `csharp-multiproject/repo/src/Web/bin/` and `src/Web/obj/` with generated `*.g.cs`,
  and `tools/bin/run.sh` plus `tools/bin/build.py` that are walked. Check with `git check-ignore` that the new
  folders are committed (add `!fixtures/repos/**/bin/` and `!fixtures/repos/**/obj/` to `.gitignore` if needed).
  Update both `expected.json` files by hand. Tests in `backend/tests/unit/test_walk.py`: `bin` next to a
  `.csproj` skipped, `bin` without one walked, `Bin`/`OBJ` casing, a `.csproj` folder (not file) does not count,
  and a test in `backend/tests/integration/test_snapshot.py` that the dirty-tree hash ignores the skipped `obj/`.

**Checkpoint**: all stories pass.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T015 [P] Add `backend/tests/integration/test_safety_cs.py` (constitution I, SC-007): analyzing
  `csharp-edge` and a temporary repo with `ProjectReference Include="..\..\outside\X.csproj"`, a billion-laughs
  `DOCTYPE`, and `<Import>` starts no subprocess (`subprocess.Popen`, `os.system`, `os.exec*` patched to fail),
  opens no path outside the root (patched `open`/`os.open` recorder), and finishes within one second.
- [ ] T016 [P] Extend `backend/tests/integration/test_performance.py` (marked `slow`, SC-005): generate about 1,000
  `.cs` files across 20 projects with project references, namespaces shared by several files and usings; assert
  analysis under 30 seconds and schema-valid output.
- [ ] T017 Update docs for the slice: `README.md` feature status table and quick start (C# row, `dotnet`/`nuget`
  ecosystems), `docs/product/project-context.md` § 7 (what slice 1 covers), and the C# entry in
  `specs/007-csharp-analysis/checklists/requirements.md` notes; run every scenario of
  `specs/007-csharp-analysis/quickstart.md` (scenario 6 with `make db`) and fix any drift between docs and output.

---

## Dependencies & Execution Order

### Phase dependencies

- Setup (T001–T002) → Foundational (T003–T004) → US1 (T005–T008) → US2 (T009–T013) → US3 (T014) → Polish
  (T015–T017).
- US2 builds on US1's resolver and build pass (T010 extends T006, T011 extends T007).
- US3 depends only on Foundational for the walker change, but its fixture edits need T008 and T012.

### Within stories

- T005 and T006 are independent (extractor vs resolver over plain records); T007 joins them; T008 needs T007.
- T009 is independent of US1 code; T010 needs T006 and T009; T011 needs T010; T012 and T013 need T011.

### Parallel opportunities

- T002 with T001.
- T005 with T006 (different files, both only need T003).
- T009 can start as soon as T003 is done, in parallel with all of US1.
- T015 and T016 in parallel after T014.

### Parallel example: User Story 1

```text
Task: "T005 [US1] C# extractor in backend/src/graphora/adapters/csharp/extract.py"
Task: "T006 [US1] single-scope resolution in backend/src/graphora/resolve/csharp.py"
```

### Parallel example: User Story 2

```text
Task: "T009 [US2] .csproj reader in backend/src/graphora/adapters/msbuild/csproj.py"   (alongside US1)
```

## Implementation Strategy

### MVP first (User Story 1)

1. T001–T004: schema v4 and queries, all existing tests green.
2. T005–T008: C# file graph inside one project.
3. Stop and validate: `csharp-basic` golden, determinism and query tests; quickstart scenario 1.

### Incremental delivery

- US2 adds projects and cross-project visibility; US3 adds the skip rule; each ends at a checkpoint with a green
  suite and one pushed commit per task.
- Slices 2–3 of issue #19 (type-level resolution, implicit and global usings across a project,
  `Directory.Build.props`, `.sln`, project views) get their own spec, plan and tasks on the same branch.
