# Contract: Graph format v7

Changes from v6 only.

- `schema_version`: `7`.
- An edge MAY carry `alias` when `type` is `imports` and `extractor` matches `^python-adapter@`. It is the name
  bound by `as` and differs from `symbol` (research § R2).
- All other `alias` rules stay: allowed on `reexports` and `using_alias` edges, forbidden on `type_reference`
  and `solution_member` edges.
- Python file nodes still have no `exports`.

Example:

```json
{"source": "file:pkg/__init__.py", "target": "file:pkg/server.py", "type": "imports", "form": "static",
 "symbol": "create_server", "alias": "make_server", "line": 2, "confidence": "resolved", "...": "..."}
```

Consumers updated in the same change: model validation, serializer, loader (version check), store, queries,
MCP overview (reports the version).
