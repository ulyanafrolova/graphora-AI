# Contract: graph questions over HTTP

All routes are `GET`, read-only, answer from the store only, and use the `/api/v1` error shape of
`specs/005-storage-http-api/contracts/http-api.md`. `/api/v1/hotspots` (014) is unchanged.

## Routes

| Route | Required | Optional (default) |
|---|---|---|
| `/api/v1/dependencies` | `repository`, `snapshot`, `target` | `include_type_only` (`true`), `level` (`file`), `limit` (50) |
| `/api/v1/dependents` | `repository`, `snapshot`, `target` | `symbol`, `include_type_only` (`true`), `follow_barrels` (`false`), `level` (`file`), `limit` (50) |
| `/api/v1/impact` | `repository`, `snapshot`, `target` | `max_depth`, `include_type_only` (`true`), `follow_barrels` (`false`), `level` (`file`), `limit` (50) |
| `/api/v1/neighbors` | `repository`, `snapshot`, `target` | `include_type_only` (`true`), `limit` (50) |
| `/api/v1/cycles` | `repository`, `snapshot` | `include_type_only` (`true`), `level` (`file`), `limit` (50) |
| `/api/v1/key_files` | `repository`, `snapshot` | `include_type_only` (`true`), `limit` (10) |
| `/api/v1/definitions` | `repository`, `snapshot`, `name` | `limit` (50) |
| `/api/v1/overview` | `repository`, `snapshot` | — |
| `/api/v1/projects` | `repository`, `snapshot` | — |

- `target`: a repository-relative path (`src/app.py`, `./src/app.py`), a node id (`file:src/app.py`,
  `ext:npm:react`) or an external package name (`requests`); for `level=project` also a `.csproj` path.
- `name`: an exact, case-sensitive symbol name (`User`, `App.Models.User`, `Logger.write`).
- Booleans: `true` or `false`. `limit`: 0..500. `max_depth`: ≥ 1. `level`: `file` or `project`.

## Success

`200`, `Content-Type: application/json`. The body is byte-identical to

```text
graphora query <stored graph> <question> [target] --format json --limit <effective limit> [flags]
```

(`key_files` is `key-files` in the CLI; `overview` and `projects` take no `--limit`), i.e. `results.dumps(answer)`
of the query layer. Example (`/api/v1/impact?repository=app&snapshot=3f1c…&target=src/db.py&limit=2`):

```json
{
  "completeness": {"files_with_errors": 0, "not_analyzed_files": 0, "unresolved_imports": 3},
  "items": [
    {"chain": [{"source": "file:src/api.py", "target": "file:src/db.py", "confidence": "resolved", "...": "..."}],
     "confidence": "resolved", "distance": 1, "kind": "file", "node": "file:src/api.py", "type_only": false}
  ],
  "options": {"follow_barrels": false, "include_type_only": true, "limit": 2, "max_depth": null},
  "question": "impact",
  "snapshot": "3f1c…",
  "target": "file:src/db.py",
  "total": 7,
  "truncated": true
}
```

(shape abbreviated; the authoritative fields are those of `graph/results.py`.)

## Errors

| Case | Status | `error.kind` |
|---|---|---|
| unknown parameter, parameter given twice, missing or empty required parameter | 400 | `bad_request` |
| boolean not `true`/`false`, malformed integer, `level` not `file`/`project` | 400 | `bad_request` |
| `limit` outside 0..500 | 400 | `bad_request` |
| `max_depth` < 1; `level=project` with `symbol`, `follow_barrels=true` or `include_type_only=false` | 400 | `bad_request` |
| `target` with `..`, a leading `/` or `\` | 400 | `bad_request` |
| repository not stored / snapshot not stored | 404 | `not_found` |
| target not in snapshot, skipped, `detected_only`, `not_code`, ambiguous, not a project | 404 | `not_found` |
| stored analysis with another graph schema version | 409 | `stale` |
| store unreachable | 503 | `store_unavailable` |

Messages are the query layer's or the existing API's; they name only the repository, snapshot, target or parameter
at fault. Parameter names and value syntax are checked before the store is read; the target itself is resolved
by the query layer after the graph is loaded.

## OpenAPI

`/api/v1/openapi.json` lists the nine routes with `get` only, each with its query parameters (type, required,
default, `enum` for `level`, `minimum`/`maximum` for `limit`).
