# Research: Graph Queries over HTTP

No open unknowns were left in the spec. The decisions below fix the design choices the spec left to the plan.

## R1. One route per question, built from a table

**Decision**: Each question gets its own `GET /api/v1/<question>` route: `dependencies`, `dependents`, `impact`,
`neighbors`, `cycles`, `key_files`, `definitions`, `overview`, `projects`. The routes are registered in a loop
from one table in a new module `api/questions.py`. Each table row names the query function, its target parameter
(`target`, `name` or none), the options it takes and its default limit. `/api/v1/hotspots` (014) stays where it is,
in `api/routes.py`, with its current behaviour.

**Rationale**:
- Each route validates exactly its own parameters, so "an option the question does not take" is the same check
  as "unknown parameter" (FR-007).
- The routes look like `/hotspots` and appear one by one in the OpenAPI description (FR-013).
- A table keeps nine routes in one place instead of nine copies of the same handler.
- A new module keeps the diff in Ulyana's `api/routes.py` small: only the shared helper from R4.

**Alternatives considered**:
- One route `GET /api/v1/query?question=…`: the allowed parameters depend on another parameter, so the OpenAPI
  description cannot list them, and the error for a misplaced option is less clear.
- Nine hand-written handlers: the same validation repeated nine times.
- Moving `/hotspots` into the table: possible (it fits the row shape), but the spec keeps its behaviour, including
  "no maximum limit", and it has its own tests. Left for a later cleanup.

## R2. Parameters and how they are read

**Decision**: Parameters are read with the existing `_params` helper of `api/routes.py` (exactly the named keys,
each at most once, required ones non-empty), then converted per kind:

| Kind | Parameters | Accepted values |
|---|---|---|
| text | `repository`, `snapshot`, `target`, `name`, `symbol` | any non-empty string (`symbol` may be absent) |
| boolean | `include_type_only` (default `true`), `follow_barrels` (default `false`) | exactly `true` or `false` |
| integer | `limit`, `max_depth` | the existing `_INT` pattern (up to 9 digits, optional `-`) |
| choice | `level` (default `file`) | `file` or `project` |

Which question takes which parameter is the CLI's rule (`_WITH_TARGET`, `_OPTION_QUESTIONS`, `_LEVEL_QUESTIONS` in
`cli/__init__.py`) and the MCP tool signatures:

| Question | target | Options |
|---|---|---|
| dependencies | `target` | `include_type_only`, `level`, `limit` |
| dependents | `target` | `symbol`, `include_type_only`, `follow_barrels`, `level`, `limit` |
| impact | `target` | `max_depth`, `include_type_only`, `follow_barrels`, `level`, `limit` |
| neighbors | `target` | `include_type_only`, `limit` |
| cycles | — | `include_type_only`, `level`, `limit` |
| key_files | — | `include_type_only`, `limit` |
| definitions | `name` | `limit` |
| overview | — | — |
| projects | — | — |

Options are passed to the query function only when the question takes them, with the defaults above; the query
layer then builds the same `options` object as for the CLI.

**Rationale**: the same names and spellings as the MCP tools (`include_type_only`, `max_depth`, `key_files`,
`name`), and the booleans of `/hotspots`.

**Alternatives considered**: FastAPI's declared query parameters. They would accept `1`/`yes` as booleans and
would not reject unknown or repeated keys, unlike the other `/api/v1` routes.

## R3. Limits

**Decision**: Default `limit` 50, maximum 500 (the MCP constants `DEFAULT_LIMIT`, `MAX_LIMIT`); `key_files` defaults
to 10 like the MCP tool and `/hotspots`. A limit outside 0..500 is 400 `limit must be between 0 and 500`. The
effective limit is always passed to the query function, so `options.limit` in the answer is never `null`.

**Rationale**: answers on a 5,000-file graph (an `impact` of a central file can list thousands of items) stay
bounded, the UI gets `total` and `truncated` to show "and N more", and the numbers match what agents see over MCP.

**Alternatives considered**: no default limit, as in the CLI: unbounded answers on large graphs. A maximum above
500: the UI shows at most a few hundred highlighted files anyway; the full graph is `/api/v1/graph`.

## R4. Store lookup, missing snapshots and stale analyses

**Decision**: A helper `stored_index(store, repository, snapshot)` in `api/routes.py` does the steps `/hotspots`
does today: `get_analysis`; `None` → 404 via `_missing` (repository or snapshot not found); a schema version other
than `SCHEMA_VERSION` → 409 `stale`; otherwise `queries.index(loads(graph))`. `/hotspots` is changed to call it
(same behaviour, same messages); the new routes call it too.

**Rationale**: one place for the 404/409 rules (FR-009), so the nine new routes and `/hotspots` cannot drift.

**Alternatives considered**: copying the block into the new module: two copies of the stale rule.

## R5. Errors from the query layer

**Decision**:

| Raised | Status | Kind | Message |
|---|---|---|---|
| `NodeNotFound` with status `invalid_path` | 400 | `bad_request` | the query layer's message |
| `NodeNotFound`, any other status (`not_in_snapshot`, `detected_only`, `not_code`, a skip reason, `ambiguous`, `not_a_project`) | 404 | `not_found` | the query layer's message, e.g. `vendor/x.js is skipped (vendored)` |
| `ValueError` (negative `max_depth`, `level=project` with `symbol`/`follow_barrels`/`include_type_only=false`) | 400 | `bad_request` | the query layer's message |

Validation happens before the store is read, so a malformed request never costs a graph load. Option combinations
are checked by the query layer (`_project_level`, `_check_depth`), not repeated in the route.

**Rationale**: the same reasons the CLI prints (spec US1 scenario 3); the messages name only the target and the
option at fault (FR-011). `ambiguous` stays 404: the target as written does not name one node.

**Alternatives considered**: a new error kind per `NodeNotFound` status: more surface for the frontend with no use
in the first slice; the message already says why.

## R6. No cache between requests

**Decision**: Each request reads the stored graph and builds the index, as `/hotspots` does. No cache in this slice.

**Rationale**:
- 004 SC-004 measured < 2 s for loading and indexing a 5,000-file graph and < 1 s per query, which meets this
  spec's SC-003 (< 3 s per request, store read included). A slow test checks it (R8).
- A stored analysis can be replaced for the same (repository, snapshot) (014 FR-018), so a cache needs a key that
  changes with the graph bytes; that is extra work with a correctness risk and no measured need yet.

**Alternatives considered**: an LRU of `GraphIndex` keyed by repository, snapshot and a hash of the graph bytes.
Kept as a follow-up if the frontend finds requests too slow on large graphs.

## R7. OpenAPI description

**Decision**: Each route passes its parameter list through `openapi_extra={"parameters": [...]}` (name, `in: query`,
required, schema type, enum for `level`, minimum/maximum for `limit`, default), generated from the table of R1/R2.
`test_only_read_endpoints` in `tests/integration/test_api.py` lists the nine new paths.

**Rationale**: the handlers read `Request` directly (R2), so FastAPI cannot infer the parameters; without this the
generated description would show the routes with no parameters (FR-013).

**Alternatives considered**: a hand-written contract only: the frontend team would have to read `specs/` instead
of `/api/v1/docs`.

## R8. Tests

**Decision**:
- `tests/golden/test_http_queries.py` (`db`): for every entry of every fixture's `queries.json` (the cases the MCP
  golden test uses), store the fixture, call the route with the same options and limit 500 (as the MCP test does),
  and compare the body byte for byte with `run_query(... --format json)`; ask twice and compare (SC-001, SC-002).
  Plus `overview` and `definitions` for each fixture, which `queries.json` does not cover.
- `tests/integration/test_http_queries_api.py` (`db`): defaults (limit 50, `key_files` 10), `limit=0`, the error
  table (unknown, repeated, missing, malformed, out-of-range, option of another question, project-level
  combinations, invalid path, each `NodeNotFound` status, missing repository/snapshot, `stale`), OpenAPI parameters,
  no echo of hostile values, concurrent requests.
- `tests/integration/test_http_queries_performance.py` (`slow`, `db`): the 5,000-file graph of
  `test_query_performance.py` stored once, each question < 3 s (SC-003).
- `tests/integration/test_api.py`: the path list of `test_only_read_endpoints`.
- `tests/integration/test_hotspots_api.py` stays as it is and proves R4 kept `/hotspots` unchanged (SC-006).

**Rationale**: the byte comparison with the CLI is the spec's main promise (FR-004); the fixtures and the CLI path
are already trusted by the 004 and 006 golden tests.
