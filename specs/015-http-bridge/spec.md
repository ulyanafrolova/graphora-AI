# Feature Specification: HTTP Bridge Between Frontend Calls and Backend Routes

**Feature Branch**: `015-http-bridge`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "issue 015" — feature 015 from the team plan (`docs/product/team-workflow.md`, round
6–7, issue #36): "HTTP bridge: link frontend HTTP calls to backend routes in the analyzed repository. A
TypeScript/JavaScript call such as `fetch("/api/items")` or `axios.get("/api/items")` is matched with a Python
route such as `@app.get("/api/items")` (FastAPI) or `@app.route("/api/items")` (Flask) by method and normalized
path, and becomes an edge marked `heuristic`: a matching URL is likely, not proven. URL templates are
normalized, router prefixes are followed when they are static, and a URL built at run time is never guessed.
Analysis stays static. Open questions: which frameworks and clients the first slice covers, the schema change,
how base URLs and prefixes are resolved, and a fixture repository with hand-written expected.json. Graph only:
showing the edge in the web UI is part of the frontend work."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A frontend call is linked to the backend route it reaches (Priority: P1)

A developer analyzes a full-stack repository: a TypeScript frontend calls `fetch("/api/items")` and a Python
backend declares a route `GET /api/items`. Today the graph shows two unconnected parts. After this feature the
graph has an edge from the frontend file to the backend file that declares the route, marked as a likely link
(heuristic), with the HTTP method and path, the line of the call and the line of the route. Graph questions use
it: the impact of changing the backend route file includes the frontend file, as a likely dependent.

**Why this priority**: This is the feature. Without it, every "what breaks if I change the API" answer stops at
the language boundary, and the product's own demo ("the frontend will break" downgraded to a hypothesis) has no
heuristic link to show.

**Independent Test**: Analyze a fixture repository with matching calls and routes; compare the HTTP edges with
the fixture's hand-written expected result; check that impact of the backend file lists the frontend file as
likely.

**Acceptance Scenarios**:

1. **Given** a frontend file with `fetch("/api/items")` on line 2 and a backend file declaring `GET /api/items`
   on line 8, **When** the repository is analyzed, **Then** the graph has one HTTP edge from the frontend file
   to the backend file, confidence `heuristic`, with method `GET`, path `/api/items`, the call at line 2 and
   the route at line 8.
2. **Given** `axios.post("/api/items", body)` and a backend route `POST /api/items`, **When** analyzed,
   **Then** the edge has method `POST`; a `GET`-only route at the same path does not match a `POST` call.
3. **Given** a `fetch` call with no method option, **When** matched, **Then** it is treated as `GET`; with
   `{ method: "DELETE" }` written literally, as `DELETE`.
4. **Given** an HTTP edge into a backend file, **When** the developer asks for the dependents or the impact of
   that file, **Then** the frontend file appears, marked as likely, never as a fact.
5. **Given** a claim "the frontend calls the items API" citing the call line, **When** it is verified, **Then**
   the verdict is `heuristic` (supported by a likely link), never `verified`.
6. **Given** the same repository analyzed twice, **When** the graphs are compared, **Then** they are
   byte-identical.

---

### User Story 2 - Paths with parameters match across both languages (Priority: P1)

Routes and calls write the same URL differently: the backend declares `/users/{user_id}` (FastAPI) or
`/users/<int:user_id>` (Flask); the frontend calls `` `/users/${id}` `` or `"/users/" + id`. These are the same
endpoint and must match; `/users/{id}/orders` and `/users/me` must not be confused with it.

**Why this priority**: Most real APIs have path parameters; without normalization the bridge would only link
the simplest endpoints.

**Independent Test**: A fixture with parameterized routes and every call form; check that each call matches
exactly the expected route and nothing else.

**Acceptance Scenarios**:

1. **Given** a route `/users/{user_id}` and a call `` fetch(`/users/${id}`) ``, **When** analyzed, **Then**
   they match.
2. **Given** a Flask route `/users/<int:user_id>` and the same call, **When** analyzed, **Then** they match.
3. **Given** a call `"/users/" + id`, **When** analyzed, **Then** it is read as `/users/{param}` and matches.
4. **Given** routes `/users/me` and `/users/{id}` and a call `/users/me`, **When** analyzed, **Then** the call
   matches only `/users/me` (a literal segment beats a parameter).
5. **Given** a call with a query string or fragment (`/api/items?page=2`), **When** analyzed, **Then** the
   query and fragment are ignored for matching.
6. **Given** a trailing slash on one side only (`/api/items/` vs `/api/items`), **When** analyzed, **Then**
   they match.

---

### User Story 3 - Router prefixes and base URLs are followed when written literally (Priority: P2)

Backends mount routers under a prefix (`APIRouter(prefix="/api")` with `include_router(router, prefix="/v1")`,
or a Flask blueprint with `url_prefix="/api"`); frontends often prepend a base path kept in a constant
(`const API = "/api"; fetch(`${API}/items`)`). The bridge follows these when the values are literal strings in
the code, so `@router.get("/items")` in a router mounted at `/api` matches a call to `/api/items`.

**Why this priority**: Real projects rarely write the full path on the route itself; without prefixes many
routes never match. It builds on US1 and US2.

**Independent Test**: A fixture where routes are mounted with literal prefixes and calls use a literal base
constant; check the matches against the expected result.

**Acceptance Scenarios**:

1. **Given** `router = APIRouter(prefix="/api")` with `@router.get("/items")`, **When** analyzed, **Then** the
   route path is `/api/items`.
2. **Given** that router mounted with `app.include_router(router, prefix="/v1")` in the same repository,
   **When** analyzed, **Then** the route path is `/v1/api/items`.
3. **Given** a Flask blueprint `Blueprint("items", __name__, url_prefix="/api")` with `@bp.route("/items")`,
   **When** analyzed, **Then** the route path is `/api/items`.
4. **Given** `const API = "/api"` at the top level of a frontend file and `` fetch(`${API}/items`) `` in the same
   file, **When** analyzed, **Then** the call path is `/api/items`.
5. **Given** a prefix or base that is not a literal string in the code (read from configuration or an
   environment variable), **When** analyzed, **Then** the bridge does not guess it: routes keep the part it
   knows and the call is recorded as not resolvable (US4).

---

### User Story 4 - What cannot be matched is reported, never guessed (Priority: P2)

Not every call can be linked: the URL is built at run time, it goes to another host, no route matches, or more
than one route matches. The developer sees each such call recorded honestly, with the reason, so the coverage of
the bridge is visible and nothing is invented.

**Why this priority**: The constitution forbids guessing targets; an honest "unresolved" is part of the product's
claim. It also tells the developer why an expected link is missing.

**Independent Test**: A fixture with each kind of unmatched call; check that each is recorded with the right
reason and that no edge points to a backend file for it.

**Acceptance Scenarios**:

1. **Given** a call whose URL is a variable or a function result (`fetch(url)`, `fetch(buildUrl())`), **When**
   analyzed, **Then** it is recorded as an unresolved HTTP call with the reason "dynamic".
2. **Given** a relative-path call with no matching route in the repository, **When** analyzed, **Then** it is
   recorded as unresolved with the reason "not found", showing the method and normalized path.
3. **Given** a call that matches routes in two different backend files equally well, **When** analyzed,
   **Then** it is recorded as unresolved with the reason "ambiguous" and no edge to either file.
4. **Given** a call to an absolute URL on another host (`https://api.github.com/...`), **When** analyzed,
   **Then** it is not recorded at all: it is not part of this repository's API.
5. **Given** a backend route that no frontend call reaches, **When** analyzed, **Then** nothing is recorded
   for it; routes are only used as targets.

---

### Edge Cases

- A repository with only a backend or only a frontend: no HTTP edges, nothing else changes.
- The same call appears twice on different lines: two edges (one per call line), as for imports.
- A route declared for several methods (`@app.route("/x", methods=["GET", "POST"])`, `@app.api_route`):
  matches calls of any listed method; Flask's default is `GET`.
- A method written as a variable (`fetch(url, { method: m })`): the call is "dynamic" for the method and is
  matched as any method only if exactly one route has that path; otherwise ambiguous.
- Calls inside test files or mock servers are treated like any other code; the coverage report already shows
  which files are tests.
- Text that looks like a route inside a comment or a string that is not passed to a call or decorator is
  ignored.
- `fetch` or `axios` names that are shadowed or imported from somewhere unexpected (a local function named
  `fetch`): the bridge matches by call form only and says so in its extractor documentation; this is why the
  edge is heuristic.
- Very large repositories: matching all calls against all routes must not change the analysis time noticeably.

## Requirements *(mandatory)*

### Functional Requirements

**Routes (backend)**

- **FR-001**: The analysis MUST find routes declared in Python with FastAPI-style decorators on an application
  or router object (`get`, `post`, `put`, `patch`, `delete`, `head`, `options`, `api_route`) and Flask-style
  decorators (`route` with an optional literal `methods` list, and `get`/`post`/… shortcuts), recording for
  each: HTTP methods, path, file and line.
- **FR-002**: Route paths MUST include literal prefixes from the router or blueprint declaration and from the
  mount call (`include_router(..., prefix=...)`, `register_blueprint(..., url_prefix=...)`) when those are
  literal strings in the repository; a non-literal prefix MUST NOT be guessed.

**Calls (frontend)**

- **FR-003**: The analysis MUST find HTTP calls in TypeScript and JavaScript written as `fetch(url, options?)`
  and `axios.<method>(url, ...)` / `axios({ url, method })`, recording method, URL form, file and line.
- **FR-004**: A call URL MUST be read when it is a string literal, a template literal, a concatenation of string
  literals and expressions, or such a form starting with a top-level constant of the same file whose value is a
  string literal; interpolated expressions inside the path become parameters. Any other URL is "dynamic".
- **FR-005**: The method MUST come from the call form (`axios.post`) or a literal `method` option; a missing
  method in `fetch` is `GET`.

**Matching**

- **FR-006**: Paths MUST be normalized before matching: query and fragment removed, trailing slash removed,
  every parameter form (`{name}`, `{name:type}`, `<name>`, `<type:name>`, interpolations, concatenated
  expressions) turned into one parameter marker.
- **FR-007**: A call MUST match a route when the methods agree and the normalized paths agree segment by segment,
  where a parameter matches any one segment; when several routes match, routes with more literal segments in the
  same positions win; if the winners are in more than one file, the call is ambiguous.
- **FR-008**: Each matched call MUST become an edge from the calling file to the file declaring the route, with
  confidence `heuristic` and its own reason (a matched HTTP route), the call line, the route line, method and
  normalized path, and the full provenance every edge carries.
- **FR-009**: Calls that cannot be matched MUST be recorded as unresolved with a reason from a fixed list
  (dynamic, not found, ambiguous) and the method and path where known; calls to absolute URLs on another host
  MUST NOT be recorded.
- **FR-010**: Analyzed code MUST NOT be executed; configuration and environment files are not read to resolve
  prefixes or base URLs.

**Graph contract and consumers**

- **FR-011**: The graph contract MUST gain the HTTP edge and its unresolved form, with a new schema version;
  every consumer (graph queries, store, HTTP API, MCP server, verifier, agents) MUST accept the new version in
  the same change.
- **FR-012**: Graph questions (dependents, impact, neighbors, cycles) MUST include HTTP edges as heuristic links,
  exactly like other heuristic edges, and MUST allow excluding them the same way.
- **FR-013**: The verifier MUST give a claim that relies on an HTTP edge the status `heuristic`, never
  `verified`.
- **FR-014**: Output MUST stay deterministic: HTTP edges and unresolved calls sorted like other edges.

**Quality**

- **FR-015**: A fixture repository MUST cover every acceptance scenario of US1–US4 with a hand-written expected
  result; the existing `mixed-fullstack` fixture's expected result MUST be updated (its `/api/items` call has no
  route and becomes "not found").
- **FR-016**: Every existing fixture MUST still produce its expected graph apart from the schema version and the
  new HTTP entries.

### Key Entities

- **Route**: a backend endpoint: methods, normalized path, file, line.
- **HTTP call**: a frontend request: method, URL form (literal, template, concatenation, dynamic), normalized
  path, file, line.
- **HTTP edge**: a heuristic link from a calling file to a route's file, with method, path, call line and route
  line, plus standard provenance.
- **Unresolved HTTP call**: a call recorded with its reason (dynamic, not found, ambiguous) and what is known of
  its method and path.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the bridge fixture, 100% of the hand-written expected HTTP edges are found and no other HTTP edge
  is produced.
- **SC-002**: 100% of the expected unresolved calls are recorded with the expected reason; no call is linked to a
  route the expected result does not list.
- **SC-003**: No HTTP link is ever presented as a fact: every HTTP edge is heuristic in the graph, in graph
  answers, in verifier verdicts and in agent answers.
- **SC-004**: Analysis time of every existing fixture and of the performance test repository grows by less than
  10%.
- **SC-005**: Two analyses of the same snapshot give byte-identical graphs.
- **SC-006**: For the product's demo question on a full-stack fixture ("will the frontend break if I change the
  items API?"), the agents can support the claim only as likely, with the call and route lines cited.

## Assumptions

- The first slice covers FastAPI and Flask on the backend and `fetch` and `axios` on the frontend; Django,
  Express, other HTTP clients (`ky`, generated API clients), GraphQL and WebSocket are out of scope and can be
  added later as extractors.
- Matching is within one analyzed repository; calls to other repositories or services are out of scope.
- Base URLs are resolved only from top-level string constants in the calling file; values imported from other
  files or read from configuration are treated as unknown.
- The HTTP edge goes from the calling file to the route's file; a symbol-level link (to the handler function) is
  out of scope for this slice; the route line is recorded so the UI and agents can point at it.
- Showing HTTP edges in the web UI is part of the frontend work, not this feature.
- No new command, endpoint or MCP tool is added; the edges appear through the existing ones.
