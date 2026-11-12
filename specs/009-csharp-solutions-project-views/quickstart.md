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

- `projects` lists every project with its solutions; one project is in no solution, and project-less files are
  counted in the last entry;
- `Web`'s dependencies show `Infra` and `Core` with a cited file and line, and `Tools` as
  "(declared, not used by code)";
- the project-level cycle between the two loop projects is reported with an example chain.

## 4. Performance

```
uv run pytest -m slow -k "csharp"
```

Project-level `impact` and `cycles` on 1,000 files in 20 projects stay under 2 seconds (SC-005).

## 5. Store and API (optional)

```
uv run pytest -m db
```
