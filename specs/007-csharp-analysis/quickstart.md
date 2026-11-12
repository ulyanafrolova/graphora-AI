# Quickstart: Validate C# Analysis, Slice 1

Run guide for reviewers. Expected shapes are defined in [data-model.md](data-model.md) and
[contracts/graph.schema.json](contracts/graph.schema.json); this file only says how to check them.

## Prerequisites

- `cd backend && uv sync` (installs the pinned `tree-sitter-c-sharp==0.23.5`).
- No .NET SDK, `dotnet`, MSBuild or NuGet is needed. Validation is easiest on a machine without them.
- PostgreSQL only for scenario 6 (`make db`, see `CLAUDE.md`).

## 1. Golden fixtures

```
uv run pytest tests/golden -k "csharp"
```

Expected: `csharp-basic`, `csharp-multiproject` and `csharp-edge` match their hand-written `expected.json`,
with no missing or extra nodes and edges (SC-001, SC-002).

## 2. Whole suite and schema migration

```
uv run pytest -m "not slow and not db"
```

Expected: all tests pass, including every pre-existing Python, TS/JS and mixed fixture at `schema_version` 4
(SC-003) and the contract tests with the v4 accept/reject samples.

## 3. Determinism

```
uv run pytest tests/golden -k "repeat or determinism"
```

Expected: 10 runs per C# fixture, from two absolute paths, give byte-identical output (SC-004).

## 4. Manual look at one project

```
uv run graphora analyze ../fixtures/repos/csharp-multiproject/repo --out /tmp/cs.json
uv run graphora query /tmp/cs.json dependencies src/Web/Web.csproj
uv run graphora query /tmp/cs.json dependents src/Core/Domain/Order.cs
```

Check:

- `src/Web/Web.csproj → src/Core/Core.csproj` is a `project_reference` edge with the `.csproj` line;
- `nuget:Serilog` is a dependency of the project, and `dotnet:Microsoft.AspNetCore.Mvc` is used by a Web file;
- files in `Web` that `using Core.Domain;` list the declaring files, marked "(likely)" when there are several;
- `src/Web/bin` and `src/Web/obj` appear under `coverage.skipped` with `excluded_dir`, while `tools/bin/` files
  are in `coverage.files`;
- `uv run graphora analyze ../fixtures/repos/csharp-edge/repo` warns
  `ignoring <path>: not well-formed XML or has a DOCTYPE` for exactly `Broken/Broken.csproj` and
  `Evil/Evil.csproj`; `csharp-multiproject` gives no warning.

## 5. Safety

```
uv run pytest tests/integration/test_safety_cs.py
```

Expected: analysis of a C# fixture with a `DOCTYPE`/entity `.csproj`, a `ProjectReference` to `../../outside`, and
a `<Import Project="evil.targets" />` starts no subprocess, opens no file outside the root, and expands no entity
(SC-007, constitution I).

## 6. Store and API (optional, needs PostgreSQL)

```
uv run pytest -m db -k "store or api"
uv run graphora analyze ../fixtures/repos/csharp-basic/repo --store
uv run graphora serve   # then GET the stored analysis
```

Expected: the v4 document is stored, read back byte-identical, and a v3 row for the same snapshot is not reused.

## 7. Performance

```
uv run pytest -m slow -k "csharp"
```

Expected: ~1,000 generated `.cs` files across 20 projects analyze in under 30 seconds (SC-005).
