# Quickstart: Validate C# Analysis, Slice 2

Expected shapes: [data-model.md](data-model.md), [contracts/graph.schema.json](contracts/graph.schema.json).

## Prerequisites

`cd backend && uv sync`. No .NET SDK. PostgreSQL only for scenario 5 (`make db`).

## 1. Golden fixtures

```
uv run pytest tests/golden -k csharp
```

`csharp-types` and the three updated slice-1 fixtures match their hand-written `expected.json` and
`queries.json` (SC-001, SC-003).

## 2. Whole suite

```
uv run pytest -m "not slow and not db"
```

All fixtures validate against schema v5; Python and TS/JS outputs differ from v4 only in the version (SC-006).

## 3. Manual look

```
uv run graphora analyze ../fixtures/repos/csharp-types/repo --out /tmp/types.json
uv run graphora query /tmp/types.json dependents src/App/Services/Mailer.cs
uv run graphora query /tmp/types.json dependencies src/App/Web/Controllers/HomeController.cs
```

Check:

- each dependent of `Mailer.cs` (`Endpoints.cs`, `Aliases.cs`, `HomeController.cs`) is listed at the line where it
  first writes `Mailer` (or its alias `Mail`), without "(likely)";
- `HomeController.cs` has no link to `Clock.cs`, `Envelope.cs` or `Queue.cs` (it writes only `Mailer` from
  `App.Services`); its extension-method-only `using App.Extensions;` keeps its slice-1 edge (line 4);
- `Timer` (two imported repository types) and `Task` (repository and base library) show `unresolved: ambiguous`;
- `coverage.files` shows `unresolved_type_names: 1` for `HomeController.cs` (`ILogger`, a package type).

## 4. Determinism and performance

```
uv run pytest tests/golden -k "determinism and csharp"
uv run pytest -m slow -k csharp
```

10 identical runs from two paths (SC-004); the 1,000-file test stays under 30 seconds (SC-005).

## 5. Store and API (optional)

```
uv run pytest -m db
```

v5 documents store and read back byte-identical; v4 rows are not reused.
