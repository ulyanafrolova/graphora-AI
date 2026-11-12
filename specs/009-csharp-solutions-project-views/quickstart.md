# Quickstart: Validate C# Analysis, Slice 3

Shapes: [data-model.md](data-model.md), [contracts/cli.md](contracts/cli.md).

## Prerequisites

`cd backend && uv sync`. PostgreSQL only for scenario 5.

## 1. Golden fixtures and MCP equivalence

```
uv run pytest tests/golden -k "csharp"
```

Solution nodes and edges match `expected.json`; every project-level entry in `queries.json` matches, through the CLI
and through MCP (SC-001, SC-004).

## 2. Whole suite

```
uv run pytest -m "not slow and not db"
```

## 3. Manual look

```
uv run graphora analyze ../fixtures/repos/csharp-multiproject/repo --out /tmp/multi.json
uv run graphora query /tmp/multi.json projects
uv run graphora query /tmp/multi.json dependencies src/Web/Web.csproj --level project
uv run graphora query /tmp/multi.json cycles --level project
```

Check:

- `projects` lists the seven projects with their solutions; `LoopB` is in no solution (a `(no project)` entry appears
  only when there are C# files without a project, as in `csharp-edge`);
- `Web`'s dependencies show `Core` and `Infra` with a cited file and line, `Tools` as likely (only a fallback
  `using` links them), `nuget:Serilog` (likely, by name prefix), and `nuget:Microsoft.Extensions.Logging` as
  "(declared, not used by code)"; `LoopA`'s dependencies show `Tools` the same way;
- the project-level cycle between `LoopA` and `LoopB` is reported with `Alpha.cs:7 → Beta.cs:7`.

## 4. Performance

```
uv run pytest -m slow -k "csharp"
```

Project-level `impact` and `cycles` on 1,000 files in 20 projects stay under 2 seconds (SC-005).

## 5. Store and API (optional)

```
uv run pytest -m db
```
