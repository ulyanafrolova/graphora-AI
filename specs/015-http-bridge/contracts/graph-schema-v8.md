# Contract: Graph Schema v7 → v8

Changes to `schema/graph.schema.json` (the graph contract between backend and frontend). Everything not listed
is unchanged. Model: [data-model.md](../data-model.md).

| Place | v7 | v8 |
|---|---|---|
| `schema_version` | `const 7` | `const 8` |
| edge `type` enum | `imports`, `reexports`, `project_reference`, `package_reference`, `type_reference`, `solution_member` | + `http_call` |
| heuristic `reason` enum | `namespace_spread`, `partial_type`, `package_prefix`, `msbuild_condition` | + `http_route` |
| `ecosystem` enum (unresolved nodes) | `python`, `npm`, `dotnet` (+ `nuget` for externals) | + `http` (unresolved nodes only) |
| unresolved node id pattern | `^unresolved:(python\|npm\|dotnet):.+$` | `^unresolved:(python\|npm\|dotnet\|http):.+$` |
| edge properties | — | `route_line`: integer ≥ 1, optional |
| new rule | — | `type == "http_call"` ⇒ `confidence` ≠ `resolved`; `route_line` required iff target is `file:`; an `unresolved` `http_call` has `reason` ∈ {`dynamic`, `not_found`, `ambiguous`} and target `^unresolved:http:` |

Example edge:

```json
{
  "id": "e:…", "source": "file:frontend/src/api.ts", "target": "file:backend/app/routes.py",
  "type": "http_call", "form": "static", "type_only": false, "symbol": "GET /api/items",
  "line": 2, "column": 10, "route_line": 8, "snapshot": "…", "confidence": "heuristic",
  "reason": "http_route", "extractor": "http-bridge@0.1.0", "snippet_hash": "sha256:…"
}
```

Consumers updated in the same change: serializer, loader, queries (tests only), verifier (tests only), store
(version check), every fixture `expected.json` and golden file (version bump), MCP and agents (no change).
