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
uv run graphora query /tmp/types.json dependencies src/App/Program.cs
```

Check:

- each dependent of `Mailer.cs` is listed at the line where it first writes `Mailer`, without "(likely)";
- `Program.cs` has no link to `Clock.cs` or `Queue.cs` (it writes only `Mailer`), and a "(likely)" link from its
  extension-method-only `using`;
- the file that writes `Timer` with two imported `Timer` types shows `unresolved: ambiguous`;
- `coverage.files` shows `unresolved_type_names` for the file that uses a package type.

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
