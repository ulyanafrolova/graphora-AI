---

description: "Task list for 008-csharp-type-references (slice 2 of issue #19)"
---

# Tasks: C# Analysis, Slice 2 — Type References and Project-wide Usings (Schema v5)

**Input**: Design documents from `specs/008-csharp-type-references/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/graph.schema.json, contracts/cli.md,
quickstart.md

**Tests**: Required (FR-016, constitution VIII). Each task ships its own tests: write them first, confirm they
fail, then implement.

**Commits**: one commit per task, pushed right after it, on branch `docs/constitution-csharp` (PR #22). Before each
commit, `uv run pytest -m "not slow and not db"` must pass (checked with `set -o pipefail`, not through `tail`).

**Organization**:

- US1 (P1): type references give file → file edges; `using` fallback;
- US2 (P2): project-wide usings (`global using`, implicit usings, `<Using>`, `Directory.Build.props`);
- US3 (P3): aliases in code and the alias fallback.

Schema v5 is foundational: no `type_reference` edge can be written before the schema allows it.

## Format: `[ID] [P?] [Story] Description`

Paths are relative to the repository root. Code in `backend/src/graphora/`, tests in `backend/tests/`, fixtures in
`fixtures/repos/`. Run commands from `backend/`.

---

## Phase 1: Setup (shipped data)

- [X] T001 [P] Extend `backend/scripts/gen_dotnet_namespaces.py` to also write
  `backend/src/graphora/resolve/data/dotnet_types.txt` (research R3): first line `# dotnet-types@10.0.0`, then one
  `<framework> <namespace> <type>` triple per line for every public top-level `T:` entry of the three .NET 10
  reference packs (generic arity `` `N `` dropped, nested `+` types skipped), sorted, unique, UTF-8, LF. Regenerate
  both data files; `dotnet_namespaces.txt` must not change. Add `NAMESPACES`-style loader test in
  `backend/tests/unit/test_cs_resolve.py` that `System.Collections.Generic List`, `System.Threading.Tasks Task` and
  `Microsoft.AspNetCore.Mvc Controller` (ASP.NET only) are present.
- [X] T002 [P] Create `backend/scripts/gen_implicit_usings.py` and generate
  `backend/src/graphora/resolve/data/implicit_usings.txt` (research R4): it downloads, at the pinned tags, the props
  files listed in R4 (`dotnet/sdk` `v10.0.100`: `Microsoft.NET.Sdk.CSharp.props`, `WebSdk/Web/Targets/Sdk.Server.props`,
  `WebSdk/Worker/Targets/Microsoft.NET.Sdk.Worker.props`; `dotnet/winforms` `v10.0.0`; `dotnet/wpf` `v10.0.0`), reads
  them with expat (DTDs refused), and keeps `<Using Include>` items inside an `ItemGroup` whose `Condition` tests
  `ImplicitUsings`. Output: `# dotnet-implicit-usings@10.0.100`, then `<group> <namespace>` lines with groups
  `base`, `web`, `worker`, `winforms`, sorted (WPF defines no implicit usings, so no `wpf` group). Module docstring as in the other generators (network, never run
  by tests or `analyze`). Test in `backend/tests/unit/test_cs_resolve.py`: `base` is exactly the seven namespaces
  in R4, `web` contains `Microsoft.AspNetCore.Builder`.

---

## Phase 2: Foundational (schema v5)

- [X] T003 Move the graph format to schema v5 (research R6, R8, R9; data-model.md):
  - copy `specs/008-csharp-type-references/contracts/graph.schema.json` to `schema/graph.schema.json`;
  - `backend/src/graphora/graph/model.py`: `EdgeType` adds `"type_reference"`; `Edge.__post_init__` rejects
    `directive` or `alias` on a `type_reference` edge; `CoverageFile` gains `unresolved_type_names: int | None =
    None` ("integer ≥ 0, only on `analyzed` C# files");
  - `backend/src/graphora/graph/serialize.py`: `SCHEMA_VERSION = 5`; coverage entries write
    `unresolved_type_names` only when not `None`;
  - `backend/src/graphora/graph/load.py`: reads it; `type_reference` edges need a file-node source;
  - tests: v5 accept/reject samples (the 9 in plan.md) in `backend/tests/contract/test_schema.py`, version cases in
    `backend/tests/unit/test_load.py`, `test_serialize.py`, `test_overview.py` and
    `backend/tests/integration/test_store.py`; conftest projection copies `unresolved_type_names` when present.

**Checkpoint**: suite green on v5; no type-reference output yet.

---

## Phase 3: User Story 1 - Dependencies point at the file that is really used (Priority: P1) 🎯 MVP

**Goal**: `type_reference` edges from written types; slice-1 `using` edges to files kept only as fallback.

**Independent Test**: `uv run pytest tests/golden -k "csharp-types or csharp-basic"`.

- [ ] T004 [P] [US1] Extract type references in `backend/src/graphora/adapters/csharp/extract.py`
  (`VERSION = "0.2.0"`, research R1): `CsFacts.type_refs: tuple[TypeRef, ...]` with `name` (dots, no generic
  arguments), `rooted`, `kind` (`"type"` | `"qualifier"`), `namespace` (enclosing namespace, `""` at file level),
  `type_params` (names of enclosing type parameters), `line`, `column`, `text` (the source line, trimmed); positions
  exactly as listed in R1, recursing into `type_argument_list`, `array_type`, `nullable_type`; `predefined_type`
  and type parameters skipped; qualifier candidates dropped when the identifier is declared in the file as a local,
  parameter, field or property name; `CsFacts.declared_names` not exported. Tests in
  `backend/tests/unit/test_cs_extract.py`: every position in R1, generics, `global::`, attributes, type parameters,
  `var`, `x.y.Z()` vs `Static.Call()`, `#if` branches, a syntax error.
- [ ] T005 [P] [US1] Implement type lookup in `backend/src/graphora/resolve/csharp.py`
  (`RESOLVER_VERSION = "0.2.0"`, research R2/R3, data-model.md § Resolution of a type reference): load
  `dotnet_types.txt`; `Resolver.resolve_type(path, ref, ctx, usings) -> TypeResult` walking the namespace levels
  innermost → global with the three steps of the table, aliases (`using X = …` at the matching level), the
  `XAttribute` retry for attributes, qualified-name rules, `ambiguous` for two or more distinct full names (repository
  or base library) at one step, `partial_type`, `msbuild_condition` through conditional visibility, and the directive
  each result came through (for the fallback). `usings` is the file's own directives grouped by namespace level; the
  project's global usings arrive in US2 and are an empty list here. Unit tests in new
  `backend/tests/unit/test_cs_types.py` for every row of the lookup table and each edge case in spec § Edge Cases that
  does not need project-wide usings.
- [ ] T006 [US1] Wire type references into `backend/src/graphora/graph/build.py` (depends on T004, T005;
  research R6–R8): one `type_reference` edge per (source, target) with the strongest confidence and the first
  position at that confidence, `symbol` the full type name, `extractor` `csharp-adapter@0.2.0`, snippet hash of the
  line; `unresolved:dotnet:<name>` placeholders for `ambiguous`; drop a file-level directive's slice-1 edges to
  `file:` targets when anything resolved through it (`using_static` edges always kept); `unresolved_type_names` on
  each analyzed C# coverage entry; `current_extractors()` adds `dotnet-types`; `extractor_versions.json` entries for
  the new versions. Tests in `backend/tests/unit/test_build_analyze.py` (end to end, schema-valid).
- [ ] T007 [P] [US1] `dependents --symbol` matches `type_reference` edges whose `symbol` is the name or ends in
  `.name`, in `backend/src/graphora/graph/queries.py` `_matches` (contracts/cli.md); test in
  `backend/tests/unit/test_dependents.py`.
- [ ] T008 [US1] Update by hand `fixtures/repos/csharp-basic/`, `csharp-multiproject/` and `csharp-edge/`
  `expected.json` and `queries.json` for type-reference edges, removed fallback edges and `unresolved_type_names`
  (derive each change from the fixture code, then compare with the tool; investigate every difference).
- [ ] T009 [US1] Add fixture `fixtures/repos/csharp-types/` (`repo/`, hand-written `expected.json`, `queries.json`)
  with the US1 cases of spec FR-016: same-namespace and enclosing-namespace references, every R1 position, a
  namespace used through one of three types, an extension-method-only `using`, ambiguity with a repository type and
  with a base-library type (`Task`), `partial` and nested types, generics, attributes with and without the suffix, a
  package type that stays unresolved (counted). `queries.json`: `dependents` of `Mailer.cs`, `dependencies` of
  `Program.cs` (quickstart scenario 3).

**Checkpoint**: US1 done; SC-002 holds on `csharp-types`.

---

## Phase 4: User Story 2 - Project-wide usings (Priority: P2)

**Goal**: global, implicit, `<Using>` and `Directory.Build.props` usings feed the type lookup.

**Independent Test**: `uv run pytest tests/golden -k csharp-types` with the US2 part of the fixture.

- [ ] T010 [P] [US2] Extend the reader in `backend/src/graphora/adapters/msbuild/csproj.py`
  (`VERSION = "0.2.0"`, research R5): `Using` items (`Include`, `Alias`, `Static` (`true` case-insensitive),
  `Remove`, conditional, position) and the `ImplicitUsings` property (`value` lower-cased and trimmed, conditional
  when it or its `PropertyGroup` has a `Condition`); values containing `$(` are kept raw for the resolver to ignore.
  Tests in `backend/tests/unit/test_csproj.py`.
- [ ] T011 [US2] Project usings in `backend/src/graphora/resolve/csharp.py` and `backend/src/graphora/graph/build.py`
  (depends on T006, T010; data-model.md § Project usings): nearest `Directory.Build.props` per project inside the
  root, read with the same reader (`parse_error` flag and warning when malformed); SDK group mapping from R4;
  effective global usings in the 4-step order; `global using` directives applied project-wide (project-less files:
  only their group's); conditional items → `msbuild_condition`; a global using counts as used when any file of the
  project resolves through it (fallback rule, R7). Tests in `backend/tests/unit/test_cs_types.py` and
  `backend/tests/unit/test_build_analyze.py`; CLI warning test for a broken `Directory.Build.props` in
  `backend/tests/integration/test_cli.py`.
- [ ] T012 [US2] Extend `fixtures/repos/csharp-types/` with the US2 cases of FR-016: a `Directory.Build.props` above
  two projects (one `Microsoft.NET.Sdk.Web`, one `Microsoft.NET.Sdk.Worker`) enabling `ImplicitUsings` and adding a
  `<Using>`; `<Using>` items with `Alias`, `Static` and `Remove`; a conditional `<Using>`; a `GlobalUsings.cs`; files
  with no `using` lines that reference types through each source. Update `expected.json` and `queries.json` by hand.

---

## Phase 5: User Story 3 - Aliases in code (Priority: P3)

**Goal**: references through an alias drop the alias directive's fallback edges.

**Independent Test**: `uv run pytest tests/unit/test_cs_types.py -k alias tests/golden -k csharp-types`.

- [ ] T013 [US3] Alias fallback in `backend/src/graphora/graph/build.py` and `backend/src/graphora/resolve/csharp.py`:
  a `using_alias` directive whose alias name resolved at least one reference drops its slice-1 `file:` edges (US3-1);
  an unused alias keeps them; `using static` edges stay (US3-2). Unit tests in `backend/tests/unit/test_cs_types.py`;
  add a used and an unused alias (file level and global `<Using Alias>`) to `fixtures/repos/csharp-types/` and update
  its `expected.json` by hand.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T014 [P] Extend `backend/tests/integration/test_safety_cs.py`: a `Directory.Build.props` with a `DOCTYPE` and
  one with `<Import Project="..\..\outside\x.props" />` and a `$(…)` `<Using>`; no process started, no path outside the
  root opened, both `parse_error`/ignored as specified.
- [ ] T015 [P] Extend the C# test in `backend/tests/integration/test_performance.py`: generated files also declare
  fields and `new` expressions of types from their own and the referenced project, plus a `Directory.Build.props` with
  `ImplicitUsings`; update the expected edge count by hand; still under 30 s (SC-005).
- [ ] T016 Docs: `README.md` (status row and schema diagram: `type_reference`, `unresolved_type_names`, v5),
  `docs/product/project-context.md` § 7 (slice 2 done); run every scenario of
  `specs/008-csharp-type-references/quickstart.md` (scenario 5 if PostgreSQL is available) and fix drift.

---

## Dependencies & Execution Order

- Setup (T001–T002) → Foundational (T003) → US1 (T004–T009) → US2 (T010–T012) → US3 (T013) → Polish (T014–T016).
- T004 and T005 are independent (extractor vs lookup over plain records); T006 joins them; T007 needs only T003;
  T008 and T009 need T006.
- T010 can start right after T003; T011 needs T006 and T010; T012 needs T011.
- T013 needs T011 (global aliases come from `<Using Alias>`).

### Parallel opportunities

- T001 with T002; T004 with T005 and T007; T010 alongside US1; T014 with T015.

```text
Task: "T004 [US1] type references in backend/src/graphora/adapters/csharp/extract.py"
Task: "T005 [US1] type lookup in backend/src/graphora/resolve/csharp.py"
Task: "T007 [US1] --symbol matching in backend/src/graphora/graph/queries.py"
```

## Implementation Strategy

1. MVP: T001–T009 — exact file → file edges inside files' own usings and namespaces; validate with `csharp-types`
   and the updated slice-1 fixtures.
2. US2 makes modern projects (no `using` lines) resolve; US3 finishes aliases.
3. Slice 3 (`.sln`, project views in queries, API, UI) gets its own spec on this branch.
