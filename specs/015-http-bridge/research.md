# Research: HTTP Bridge

Decisions for [spec.md](spec.md). Each one: decision, rationale, alternatives considered.

## R1. Where the bridge lives in the pipeline

**Decision**: two extraction additions and one matching step.

- `adapters/python/extract.py` also returns `routes` (decorator facts) and `prefixes` (router/blueprint
  declarations and mount calls) in `FileFacts`, from the same Tree-sitter parse.
- `adapters/js/extract.py` also returns `http_calls` and `constants` (top-level `const NAME = "<literal>"`) in
  `FileFacts`.
- A new pure module `resolve/http.py` (`HTTP_VERSION`) turns route facts into full routes (prefixes applied),
  normalizes call paths, and matches calls to routes. `graph/build.py` calls it after the Python and JS graphs
  and appends HTTP edges and unresolved nodes (`_http_graph`).

**Rationale**: no second parse; extractors stay "what is written", the resolver decides links, as for imports
(constitution IV, VII). A separate resolver version shows up in `extractors` and invalidates stored analyses
when matching rules change (005 store reuse compares extractor versions).

**Alternatives**: a post-pass that re-reads files with regexes — rejected: misses structure (decorators,
template literals) and parses twice; matching inside the adapters — rejected: needs facts from both languages.

## R2. Python route facts

**Decision**: a decorator on a function counts when it is a call `<obj>.<attr>("<literal path>", ...)` with
`attr` in `get post put patch delete head options` (methods = that one), `api_route` (literal `methods=[...]`,
default `GET`), or `route` (Flask; literal `methods=[...]`, default `GET`). `<obj>` is a plain name. A
non-literal path makes no route. Recorded: `obj`, methods (sorted, upper case), raw path, decorator line and
column, the decorator text for the snippet hash.

Prefix facts, per file:

- `NAME = APIRouter(prefix="<lit>")` / `NAME = APIRouter()` / `NAME = FastAPI(...)` / `NAME = Flask(...)`;
- `NAME = Blueprint("<name>", ..., url_prefix="<lit>")`;
- `<app>.include_router(<expr>, prefix="<lit>")` and `<app>.register_blueprint(<expr>, url_prefix="<lit>")`
  where `<expr>` is a name or `module.name`.

A router's full prefix = its own prefix + the prefix of the mount that includes it, followed through
`module.name` / imported names with the existing 017 Python resolver index (the import edges already say which
file a name comes from). Several mounts of one router give several routes. A router that is never mounted keeps its
own prefix only. A mount (or a router declaration) whose prefix is not literal makes those routes "prefix
unknown": they match nothing, and are never guessed (FR-002).

**Rationale**: covers `app.get`, `router.get` with `APIRouter(prefix=)`, `include_router(prefix=)`, Flask apps
and blueprints — the forms of FastAPI's and Flask's own tutorials — while staying literal-only.

**Alternatives**: following prefixes through function calls or settings — rejected (dynamic); Django
`urlpatterns` — out of scope (spec assumption).

## R3. JS/TS call facts

**Decision**: a `call_expression` counts when the callee is `fetch` (or `window.fetch` / `globalThis.fetch`),
`axios.<get|post|put|patch|delete|head|options|request>` or `axios(...)`. URL argument forms:

| Form | Read as |
|---|---|
| `"/a/b"`, `'/a/b'` | literal |
| `` `/a/${x}/b` `` | template: each `${…}` is a parameter, except a leading `${NAME}` where `NAME` is a top-level string constant of the file, which is substituted |
| `"/a/" + x + "/b"` | concatenation: string parts literal, other operands parameters, a leading constant substituted |
| anything else | dynamic |

Method: `axios.<m>` → `M`; `fetch(url, {method: "<lit>"})` / `axios({url, method: "<lit>"})` → that literal,
upper-cased; `fetch` without a `method` property → `GET`; a non-literal `method` → unknown (spec edge case).
URLs starting with a scheme (`http:`, `https:`, `//`) are dropped (other host, FR-009); a URL not starting with
`/` after substitution is dynamic.

**Rationale**: the forms in `fetch` and axios documentation; the leading-constant rule handles the common
`API_BASE` pattern without reading imports or config.

**Alternatives**: resolving imported constants — later (needs cross-file value tracking); recognizing any
`get(…)` method — rejected (too many false links).

## R4. Normalization and matching

**Decision**: `normalize(path) -> tuple[str, ...]` of segments: drop `?…` and `#…`, collapse `//`, strip the
trailing `/`, split; a segment that is wholly a parameter (`{x}`, `{x:path}`, `<x>`, `<int:x>`, a call
parameter) becomes `*`; a segment mixing text and a parameter (`v{n}`) becomes `*` too. The normalized path text
is `/` + segments joined, with `{}` for `*` (e.g. `/users/{}`).

Matching a call (method `m`, segments `c`) against routes with `m` in methods (or any method when the call's
method is unknown) and equal segment count: a segment matches when equal or either side is `*`. Among matches,
a route scores one point per position where its segment is literal; the highest score wins, ties broken by
the earliest literal position (so `/users/me` beats `/users/{id}`). If all winners are in one file, the call gets
one edge to that file (route line = the first winner's line); winners in two or more files → `ambiguous`. No match →
`not_found`. An unknown method with matches in one file → edge; in more → `ambiguous`.

**Rationale**: the "literal beats parameter" rule is how FastAPI and Flask themselves pick between `/users/me`
and `/users/{id}`; file-level ambiguity is the only kind that changes the graph.

**Alternatives**: regex matching of raw strings — rejected (parameter syntaxes differ); emitting edges to all
candidates — rejected by constitution IV (no guessing).

## R5. Graph representation (schema v8)

**Decision**:

- New edge `type`: `http_call`, from `file:<frontend>` to `file:<backend>` with `confidence: heuristic`,
  `reason: http_route`, `symbol: "<METHOD> <normalized path>"` (e.g. `GET /users/{}`), `line`/`column` of the
  call, `snippet_hash` of the call text, `extractor: http-bridge@<HTTP_VERSION>`, and new field `route_line`
  (the route decorator's line in the target file). `form: static`, `type_only: false`.
- Unresolved calls: an edge `http_call` to `unresolved:http:<METHOD> <path>` (`?` for an unknown method or a
  dynamic path, e.g. `unresolved:http:GET ?`) with `confidence: unresolved` and `reason` `dynamic`,
  `not_found` or `ambiguous` (existing unresolved reasons); the node is an `UnresolvedNode` with ecosystem
  `http`.
- Schema v7 → v8: add `http_call` to edge types, `http_route` to heuristic reasons, `http` to unresolved-node
  ecosystems and the `unresolved:http:` id pattern, optional `route_line` (integer ≥ 1, required exactly for
  `http_call` edges with a `file:` target). `SCHEMA_VERSION = 8`.

**Rationale**: `symbol` already takes part in edge ids, sorting and the `dependents(symbol=…)` filter, so
`dependents("backend/app/api.py", symbol="GET /api/items")` works with no query change; `route_line` gives the
UI and agents the second line without a symbol-level edge. Using `unresolved` for unmatched calls keeps the
coverage honest and visible in `overview`.

**Alternatives**: a separate `http_routes` section in the document — rejected: every consumer would need new
code; a node per route — rejected for this slice (spec: file-level edges).

## R6. Consumers

**Decision**: the change is mostly data; consumers get:

- `graph/model.py`: `EdgeType` + `http_call`, `HeuristicReason` + `http_route`, `Ecosystem` + `http`,
  `Edge.route_line: int | None = None`;
- `graph/serialize.py` / `graph/load.py`: v8, `route_line` written when set and read back;
- `graph/queries.py`: no logic change — `dependents`, `impact`, `neighbors`, `cycles` already follow every
  file-to-file edge and keep its confidence; tests prove HTTP edges appear as heuristic. The `symbol` filter
  applies as is. Project-level views (C#) ignore `http_call` like other non-project edges.
- `verify/graph_checks.py`: no change — a dependency claim on the call line finds the heuristic edge and is
  `heuristic` (FR-013); tests prove it.
- `store`: stored v7 analyses are not reused (version check) and are re-analyzed on the next `--store` run; the
  HTTP API serves stored bytes as stored. `mcp`, `agents`: no change.

Spec FR-012 says HTTP edges can be excluded "the same way" as other heuristic edges: there is no such option for
any heuristic edge today, so the plan keeps that parity (none) and the spec wording is adjusted.

## R7. Fixtures and golden tests

**Decision**: new fixture `fixtures/repos/http-bridge/` with `backend/` (FastAPI app with `APIRouter(prefix)`
and `include_router(prefix)`, a Flask blueprint with `url_prefix`, parameter routes, `/users/me` vs
`/users/{id}`, a multi-method route, the same path in two files for ambiguity) and `frontend/` (fetch and
axios calls in every URL form, a base constant, a dynamic URL, an absolute URL, an unmatched path), and a
hand-written `expected.json`. `mixed-fullstack/expected.json` gets its `GET /api/items` as `not_found`. Every
`expected.json` and golden file moves to `schema_version: 8`; no other change is allowed (FR-016).

## R8. Performance

**Decision**: routes are indexed by (segment count, method); each call compares only against that bucket. The
performance test (`tests/integration/test_performance.py`) runs unchanged and must stay within 10% (SC-004).
