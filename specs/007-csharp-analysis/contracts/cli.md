# CLI, Query and HTTP Contract Changes: C# Analysis, Slice 1

No command, flag, exit status or endpoint is added or removed. The contracts of
[001](../../001-python-graph-cli/contracts/cli.md), [003](../../003-ts-js-analysis/contracts/cli.md),
[004](../../004-graph-queries/contracts/cli.md) and [005](../../005-storage-http-api/contracts/cli.md) apply, with
these changes.

## `graphora analyze`

- Output is schema v4 ([graph.schema.json](graph.schema.json)) for every language.
- `.cs` files are analyzed; `.csproj` files are read as data (see [data-model.md](../data-model.md)).
- Warnings (stderr, exit status unchanged) gain one line per `.csproj` with `parse_error`, in the existing
  format: `ignoring <path>: not well-formed XML or has a DOCTYPE`. Warnings stay a sorted list of paths (as
  stored by 005); the message is chosen by file type.
- `--store`: a stored v3 analysis of the same snapshot is not reused (its schema version differs); the snapshot
  is analyzed again and the row replaced, through the existing version check.

## Query commands and HTTP API (004, 005)

- A target may be the path of a `.csproj` (→ `project:<path>`), and an external name may be a NuGet package id
  or a base-library namespace. Name lookup order for externals: `npm`, `python`, `nuget`, `dotnet`; more than one
  match is the existing `ambiguous` error listing the qualified ids (`nuget:Serilog`, …).
- `dependencies`, `dependents`, `neighbors` and `impact` follow C# `imports` edges like any other import edge;
  `heuristic` items keep the existing "(likely)" mark. On a project node they follow `project_reference` and
  `package_reference` edges.
- `cycles` and `key_files` stay file-only: project edges are not mixed into file cycles.
- Text output prints `project:` and `ext:` ids by name (`src/Core/Core.csproj`, `nuget:Serilog`,
  `dotnet:System.Linq`).

## MCP server (006, merged into `main` before this feature)

- `graph_overview` counts project nodes: `nodes` gains `"project"`, and `schema_version` is 4.
- `find_definitions` finds C# types and methods by short or fully qualified name (`User`, `App.Models.User`);
  its description lists the C# kinds.
- Every other tool takes the same targets as `graphora query` (above), so `.csproj` paths and `nuget`/`dotnet`
  names work there too.
