# Data Model: Graph Queries over HTTP

No new stored data and no graph schema change. The feature adds one in-code table and reuses existing documents.

## Question (in-code table, `api/questions.py`)

One row per HTTP question (research R1, R2).

| Field | Type | Meaning |
|---|---|---|
| `name` | str | route name and `question` of the answer: `dependencies`, `dependents`, `impact`, `neighbors`, `cycles`, `key_files`, `definitions`, `overview`, `projects` |
| `ask` | callable | the `graph.queries` function |
| `target` | `"target"` \| `"name"` \| None | the required parameter passed positionally, if any |
| `options` | tuple of str | the optional parameters it takes, in signature order |
| `default_limit` | int \| None | 50, 10 for `key_files`, None for `overview` and `projects` (no `limit` parameter) |

Rules:
- Allowed parameters of a route = `repository`, `snapshot`, the target parameter, `options`, and `limit` when
  `default_limit` is not None. Anything else is 400.
- Rows are sorted by name; routes are registered in that order, so the OpenAPI description is stable.

## Option kinds

| Option | Kind | Default | Valid |
|---|---|---|---|
| `include_type_only` | boolean | `true` | `true`, `false` |
| `follow_barrels` | boolean | `false` | `true`, `false` |
| `symbol` | text | absent | non-empty |
| `max_depth` | integer | absent | ≥ 1 (checked by the query layer) |
| `level` | choice | `file` | `file`, `project` |
| `limit` | integer | row default | 0..500 |

## Reused documents

- **Query answer**: `graph.results.Answer` / `Overview`, serialized with `results.dumps` (sorted keys, 2-space
  indent, trailing newline). The HTTP body is these bytes unchanged (FR-004).
- **API error**: `{"error": {"kind": …, "message": …}}` from `api/errors.py`; kinds used here: `bad_request` (400),
  `not_found` (404), `stale` (409), `store_unavailable` (503), `internal` (500).
- **Stored analysis**: `store.StoredAnalysis` (repository, snapshot, schema version, graph bytes), read only.

## Request flow

```text
parameters ──(_params, kinds, limit range)──> 400 on error
     │
     ▼
stored_index(store, repository, snapshot) ──> 404 missing │ 409 stale
     │
     ▼
graph.queries.<question>(ix, [target], **options) ──> 400 ValueError / invalid_path │ 404 NodeNotFound
     │
     ▼
200 application/json, body = results.dumps(answer)
```
