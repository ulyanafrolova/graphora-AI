# Data Model: HTTP Bridge

Research references: [research.md](research.md).

## Extraction facts (frozen dataclasses)

### Python (`adapters/python/extract.py`, added to `FileFacts`)

| Type | Fields | Rule |
|---|---|---|
| `RouteFact` | `obj`, `methods: tuple[str, ...]`, `path`, `line`, `column`, `text` | decorator `<obj>.<verb>("<lit>")`, `.route`, `.api_route`; methods sorted, upper case; non-literal path → no fact |
| `RouterFact` | `name`, `kind` (`app` \| `router` \| `blueprint`), `prefix: str` | `NAME = FastAPI()/Flask()/APIRouter(prefix=)/Blueprint(url_prefix=)`; `prefix` `""` when absent; non-literal prefix → `prefix=None` |
| `MountFact` | `app`, `target` (name or `module.name`), `prefix: str \| None`, `line` | `include_router` / `register_blueprint`; `None` when not literal |

### JS/TS (`adapters/js/extract.py`, added to `FileFacts`)

| Type | Fields | Rule |
|---|---|---|
| `HttpCallFact` | `method: str \| None`, `parts: tuple[Part, ...] \| None`, `absolute: bool`, `line`, `column`, `text` | `fetch`, `axios.<m>`, `axios({...})`; `parts=None` for a dynamic URL; `method=None` when non-literal |
| `Part` | `kind` (`text` \| `param` \| `const`), `value` | template/concatenation pieces in order |
| `constants` | `dict[str, str]` | top-level `const NAME = "<literal>"` only |

## Resolver (`resolve/http.py`)

| Type | Fields |
|---|---|
| `Route` | `file`, `methods`, `segments: tuple[str, ...]` (`*` = parameter), `path` (display, `{}` for params), `line` |
| `Match` | `call file`, `call fact`, result: `("edge", route file, route line)` or `("unresolved", reason)` |

Functions: `normalize(text) -> tuple[str, ...]`, `routes(py_facts, import_index) -> list[Route]`,
`call_path(fact, constants) -> tuple[str, ...] | None`, `match(call, routes) -> Match`.

Reasons: `dynamic` (no path), `not_found` (no candidate), `ambiguous` (best matches in ≥ 2 files, or unknown
method matching in ≥ 2 files).

## Graph (schema v8)

`Edge` gains `route_line: int | None` (set exactly for `http_call` edges to a `file:` node).

| Field | HTTP edge | Unresolved HTTP call |
|---|---|---|
| `type` | `http_call` | `http_call` |
| `source` | `file:<calling file>` | same |
| `target` | `file:<route file>` | `unresolved:http:<METHOD or ?> <path or ?>` |
| `confidence` / `reason` | `heuristic` / `http_route` | `unresolved` / `dynamic` \| `not_found` \| `ambiguous` |
| `symbol` | `<METHOD> <path>`, e.g. `GET /users/{}` | same as the target ref |
| `line`, `column` | the call | the call |
| `route_line` | the route decorator line | absent |
| `extractor` | `http-bridge@<HTTP_VERSION>` | same |
| `snippet_hash` | of the call text | same |

Unresolved node: `UnresolvedNode(ref="<METHOD or ?> <path or ?>", ecosystem="http")`.

`extractors` gains `"http-bridge": HTTP_VERSION`; `python-adapter` and `js-adapter` versions go up (new facts).

## Validation

- `route_line ≥ 1`; present iff `type == "http_call"` and target starts with `file:`.
- `http_call` edges are never `resolved`.
- Calls with an absolute URL produce nothing.
