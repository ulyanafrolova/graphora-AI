# CLI, Query, HTTP and MCP Contract Changes: C# Analysis, Slice 2

No command, flag, endpoint or tool is added or removed. Contracts of 001–007 apply with these changes.

- `graphora analyze`: output is schema v5 ([graph.schema.json](graph.schema.json)) for every language. Warnings
  gain `Directory.Build.props` files that are not well-formed XML or have a `DOCTYPE`, in the slice-1 format
  (`ignoring <path>: not well-formed XML or has a DOCTYPE`).
- `--store`: v4 analyses are not reused (schema version differs), as before.
- Queries (CLI, HTTP, MCP): `type_reference` edges are links like import edges, so `dependencies`, `dependents`,
  `impact`, `neighbors`, `cycles` and `key_files` follow them. `dependents --symbol X` also matches a
  `type_reference` edge whose `symbol` is `X` or ends in `.X`. Text output marks them like other edges; a link
  made only of `heuristic` edges keeps the "(likely)" mark.
- MCP `graph_overview`: `schema_version` 5; counts unchanged in shape.
