# Research: Web UI

Decisions for `specs/019-frontend/spec.md` (with the five clarifications of 2026-11-26). Each: decision, rationale,
alternatives.

## R1. Frontend stack

**Decision**: `frontend/` with Vite 7, React 19, TypeScript (strict), React Router (URL state), TanStack Query
(server state and caching), Cytoscape.js with the `cytoscape-fcose` layout (compound nodes for components), `d3-hierarchy`
for the hotspot treemap layout, Shiki `codeToTokens` with its JavaScript regex engine for code colouring, `idb` for
IndexedDB. npm with a committed
`package-lock.json`; Node 22 LTS (`.nvmrc`, `engines`).

**Rationale**: the constitution fixes React + Vite + TypeScript + Cytoscape.js. fcose lays out compound graphs well and
deterministically with a fixed seed. TanStack Query gives retries, caching per (repository, snapshot) and loading /
error states without hand-written stores. `d3-hierarchy` only computes rectangles (a view operation). Shiki's
`codeToTokens` returns tokens, not HTML, so code is rendered as React text nodes (constitution VI). Shiki is created
with `createJavaScriptRegexEngine()` instead of the default Oniguruma WASM engine, so the CSP of R12 needs no
`'wasm-unsafe-eval'`.

**Alternatives**: Redux/Zustand for server data (more code, no gain); Prism/highlight.js (return HTML strings that would
need `dangerouslySetInnerHTML`); pnpm/yarn (one more tool for the team; npm ships with Node); D3 force graph instead of
Cytoscape (constitution names Cytoscape).

## R2. What the UI may compute

**Decision**: The UI never walks links. It may only: lay out and draw; filter what is shown (tests, externals); fold and
unfold components; sort, group and count items of one or more API answers (impact items per component, sum of line
counts per component, rank of a file in the `key_files` answer); normalise a score to a colour. Anything that follows
links (dependents, impact, cycles, components, centrality, hotspots, cut suggestions, claim statuses) comes from the
service.

**Rationale**: constitution V and VII forbid reimplementing graph queries; grouping and counting answer items is
presentation, the same as `render_text` does on the backend. Writing the rule down keeps reviews concrete. An ESLint
boundary rule keeps graph-walking helpers out of `frontend/src/` (no imports of a graph library other than Cytoscape for
drawing; Cytoscape's traversal APIs (`bfs`, `dijkstra`, `predecessors`, `successors`) are banned by a lint rule).

**Alternatives**: computing small things client-side (neighbours from `/graph`) for speed: rejected, the 018 routes
answer in < 0.5 s.

## R3. Components (backend, FR-021)

**Decision**: `queries.components(ix, *, include_type_only=True)` in `graph/queries.py`:

- Graph: undirected, file nodes only, one edge per linked file pair, weight = number of import edges in both directions
  (resolved and heuristic links; unresolved and externals left out). Nodes and edges are added in sorted order.
- Partition: `networkx.community.louvain_communities(g, weight="weight", resolution=1, seed=0)`; each community sorted
  by path; communities ordered by their first path. Links of a file to itself do not connect files. Files with no
  links to other files (package `__init__.py`, unrelated scripts) join the linked component whose name is their folder
  or a parent folder of it (the longest such name, ties by component order); the others are grouped into one component
  per top-level folder (`.` for root files). A component keeps the name computed from its linked files.
- Name (clarification Q5): longest common folder of the files; if none, the most frequent top-level folder (ties by
  path order; a root file counts as `.`); duplicate names get ` · 2`, ` · 3`, … in component order.
- Id: `component:<n>`, 1-based in component order.
- Per component: files, file count, direct dependents and dependencies counted between components, `has_cycle` (a
  cycle group of `cycles` lies inside it).
- Links between components: one per ordered pair, with `imports` (number of file links), `heuristic` (how many of them
  are heuristic), `in_cycle` (some cycle group has files in both components), sorted by source then target.
- Answered by CLI `graphora query <graph> components`, MCP tool `components`, HTTP `GET /api/v1/components`, byte-equal
  like 018.

**Rationale**: Louvain is named in the product docs; the seed and sorted insertion make it repeatable (constitution II).
NetworkX is pinned in `uv.lock`, so the partition is stable for a given lock; golden tests pin it on fixtures. Lines of
code are not part of the answer (the graph document has no line counts); the UI sums FR-023 line counts per component
(R2), which keeps the graph schema unchanged.

**Alternatives**: folder grouping only (no community detection; rejected by the spec); adding line counts to the graph
document (schema v9 bump, every fixture and consumer changes, for a number the store already has); label propagation
(less stable partitions).

## R4. Cycle cut suggestion (backend, FR-022, clarification Q1)

**Decision**: Each `CycleGroup` of `queries.cycles` gets `suggested_cut`: `{"method": "exact" | "greedy", "links": [Link, …]}`.

- Candidate links: the file links inside the group (same graph as the group, respecting `include_type_only`).
- Cost of a set: (number of links, total import edges in the links, sorted list of (source, target)), compared in that
  order.
- `exact` for groups of up to 20 files: search sets of size 1, 2, … in a fixed order (links sorted by cost, then path);
  the first size with a set that leaves the group acyclic wins, best cost among that size. The search has a budget of
  200,000 acyclicity checks; if it runs out, the group falls back to `greedy` and says so.
- `greedy` otherwise: repeatedly remove the link on the most simple cycles of what remains (cycles counted with
  `nx.simple_cycles` up to 10,000 per round, else the link with the highest in-group degree product), ties by fewest
  import edges then path, until no cycle is left.
- Project-level cycles (`level=project`) get no `suggested_cut` in this feature.

**Rationale**: matches the clarification (exact minimum for small groups, greedy for large) and stays deterministic and
bounded in time on 5,000-file graphs. The spec text is refined to mention the budget fallback.

**Alternatives**: exact dynamic programming over vertex orderings (2^n states: too slow in Python at n = 20); integer
programming (new dependency).

## R5. Line counts (backend, FR-023)

**Decision**: `Store.list_files(repository, snapshot) -> list[(path, has_text, line_count)]` sorted by path, and
`GET /api/v1/files?repository&snapshot` → `{"files": [{"path", "has_text", "line_count"}]}` (404 / 409 like 018).
CLI and MCP are not changed (the line counts live only in the store).

**Rationale**: one indexed query on the existing `files` table; no schema change.

**Alternatives**: one `/file` request per tile (5,000 requests); line counts in the graph (R3).

## R6. Service info (backend, FR-024)

**Decision**: `GET /api/v1/info` → `{"version", "ask": {"enabled", "model"}, "jobs": {"enabled", "limits"},
"mcp_tools": [{"name", "description"}]}`. `model` is the `provider:model` setting of `AskService`, `null` when asks are
off. `jobs.limits` are the analysis limits the running service applies (the six limit keys of 010 and the skipped
folder names), `null` when jobs are off; the Import screen shows these, never defaults kept in the UI (constitution IV).
`mcp_tools` lists the tool names and descriptions of `mcp/server.py` in store mode, the mode the MCP page tells users
to run, so `read_lines` is included (one source of truth for the MCP page, FR-019).

**Rationale**: the header badge, Import limits, Ask agents and the MCP page need facts only the service knows; no secrets are exposed
(the setting is a model name, never a key).

**Alternatives**: hard-coding tool names in the UI (drifts from the server).

## R7. Serving the built UI (FR-025, clarification Q3)

**Decision**: `graphora serve --ui DIR` (default: `$GRAPHORA_UI_DIR`, else `frontend/dist` next to the repository when
it exists). When present, `create_app` mounts it after all `/api/v1` routers: real files from the folder (Starlette
`StaticFiles`, which rejects path traversal), and `index.html` for any other `GET` path not under `/api/`, so client
routes reload correctly. Without a build, nothing changes. `/api/...` unknown paths keep the JSON 404.

**Rationale**: one command, one address for demos; no CORS; static files only.

**Alternatives**: a separate nginx container (more infrastructure); dev server only (Node needed for demos).

## R8. API client and types

**Decision**: TypeScript types for the graph document are generated from `schema/graph.schema.json` with
`json-schema-to-typescript` into `frontend/src/api/graph.gen.ts` (committed; CI fails when it is out of date). Types for
query answers, jobs, ask events, info and errors are written by hand in `frontend/src/api/types.ts` from the contracts of
004/005/010/013/014/018/019. One `api` module wraps `fetch` (base `/api/v1`, query building, error body → typed
`ApiError` with `kind`).

**Rationale**: the handlers return raw JSON bytes, so the OpenAPI description has parameters but no response schemas; the
graph schema is the one machine-readable contract.

**Alternatives**: OpenAPI code generation (no response schemas to generate from).

## R9. Ask stream

**Decision**: `POST /api/v1/ask` is read with `fetch` and a small hand-written server-sent-events parser over the
response stream (`event:`, `id:`, `data:` lines). `step` events append to the live view; `answer` ends it; `error` shows
its message. `429 busy` and `503 model_unavailable` before the stream are shown with retry (FR-006). An `AbortController`
cancels on navigation.

**Rationale**: `EventSource` cannot send POST bodies; the parser is ~40 lines and unit-tested.

**Alternatives**: a third-party SSE client (more dependency surface for a trivial format).

## R10. Agent history (FR-018a, clarification Q4)

**Decision**: IndexedDB database `graphora`, store `answers`, key `[repository, snapshot, created]`; value = the
`answer` event document plus question and time. After each insert, entries beyond the newest 20 for that snapshot are
deleted. "Clear history" deletes the snapshot's entries. If IndexedDB is unavailable, the UI keeps answers in memory and
shows "history will not be kept".

**Rationale**: localStorage is limited to ~5 MB and synchronous; traces can be large.

## R11. Large graphs and rendering

**Decision**: System level draws components only (≤ a few hundred nodes). Expanding a component adds its files as
children of the compound node; other components stay collapsed with their component links. File level for a whole
snapshot uses Cytoscape's WebGL renderer when the snapshot has more than 1,000 files, labels hidden below a zoom
threshold, and `haystack` edges. Layout: fcose with `randomize: false`, starting from positions on a circle in node-id order (so the result is the
same on every load), computed in a Web Worker for
more than 500 nodes. Minimap: a second small Cytoscape instance (view only) synchronised with the main viewport. Export:
Cytoscape `png()`/`svg` via `cytoscape-svg`.

**Rationale**: SC-003 (overview < 5 s, expand < 1 s) on 5,000 files; constitution allows a WebGL renderer when needed.

**Alternatives**: sigma.js (second graph library); canvas-only Cytoscape at 5,000 nodes (measured slow in community
reports).

## R12. Security of rendered text

**Decision**: all repository and model text goes through React text nodes. Shiki uses the JavaScript regex engine
(R1), so no WASM and no `eval` are needed. ESLint `react/no-danger` is an error; no
`innerHTML`, no `eval`, no `new Function`; links built only from known route patterns with `encodeURIComponent`. A
Content-Security-Policy header (`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'
data: blob:`) is sent by `graphora serve` for the UI files. Tests feed `<script>`, `<img onerror>`, `javascript:` and
markdown/HTML in file contents, paths, symbol names, agent answers and repository names (SC-004).

## R13. Tests and CI

**Decision**:

- **Backend**: golden tests for `components` and `cycles` cuts on fixtures with hand-written expectations
  (constitution VIII), byte equality CLI = MCP = HTTP, `/files`, `/info`, static serving and SPA fallback, CSP header.
- **Frontend unit/component**: Vitest + Testing Library + MSW (mock service worker) for API responses; SSE parser,
  history store, URL state, legend/confidence styles, error states, hostile text.
- **End-to-end**: Playwright (Chromium) against a real service started by `backend/tests/e2e_server.py`: PostgreSQL test
  database, fixtures stored, `AskService` with the scripted model of `tests/unit/scripted_model.py`, the built UI
  served by the app (R7). Scenarios follow the user stories; one test loads a stored 5,000-file graph for SC-003.
- **CI** (`.github/workflows/checks.yml`): job `frontend` (Node 22, `npm ci`, lint, typecheck, `gen:types` drift check,
  unit tests, build); job `e2e` (PostgreSQL service, uv, Node, Playwright browsers cached, build UI, run e2e). The
  backend job is unchanged apart from the new tests.
- **Make**: `make web` (dev server on 5173 proxying to 8000), `make web-build`, `make web-test`, `make e2e`.

## R14. Repository layout and ownership

**Decision**: `frontend/` is shared (team-workflow). Backend changes: `graph/queries.py`, `graph/results.py`
(`Component`, `ComponentLink`, `CycleCut`), `mcp/server.py` (tool `components`, cycles text), `cli/__init__.py`
(`query … components`) — Anna; `api/questions.py` (`components` row), `api/routes.py` (`/files`, `/info`),
`api/__init__.py` (static UI, CSP), `store/store.py` (`list_files`) — Ulyana's modules, small changes listed in the plan's
Coordination.
