---

description: "Task list for 019-frontend"
---

# Tasks: Web UI

**Input**: Design documents from `specs/019-frontend/`

**Prerequisites**: plan.md, spec.md (5 clarifications), research.md (R1–R14), data-model.md, contracts/backend.md,
contracts/ui.md, quickstart.md

**Tests**: Required (constitution VIII; spec SC-002, SC-004, SC-006, SC-007). Within each phase write the tests first and
confirm they fail. Backend expectations (components, cuts) are written by hand from the fixture sources, never copied
from the implementation's output; if they disagree, find out why before changing either.

**Organization**: Phase 1 sets up `frontend/` and the infrastructure. Phase 2 builds what every screen needs: the
backend facts (components, line counts, info, UI serving), the e2e server, the API client and the app shell. Then one
phase per user story in spec priority order, then polish.

- US1 (P1): graph, impact, code & provenance (MVP);
- US2 (P1): import and job progress;
- US3 (P2): cycles with suggested cut, hotspots, search;
- US4 (P2): ask agents, live trace, history;
- US5 (P3): large graphs (WebGL, worker layout, minimap, filters, export);
- US6 (P3): MCP page and placeholders.

Paths are relative to the repository root. Backend code in `backend/src/graphora/`, backend tests in `backend/tests/`
(run from `backend/`), frontend in `frontend/` (run from `frontend/`). Backend comments minimal, in the style of the
existing modules; frontend the same: no comment blocks, short names, one component per file.

**Commits**: one commit after every task (a test task on its own, before its implementation); short lowercase English
messages; push at the end of each phase. Draft PR #41 is already open.

## Phase 1: Setup (frontend scaffold and infrastructure)

- [X] T001 Create `frontend/` with Vite 7 React-TS: `frontend/package.json` (name `graphora-ui`, `"private": true`,
  `"type": "module"`, `engines.node: ">=22"`, scripts `dev`, `build` (`tsc -b && vite build`), `preview`, `lint`,
  `typecheck`, `test` (`vitest run`), `e2e` (`playwright test`), `gen:types`), `frontend/.nvmrc` (`22`),
  `frontend/index.html` (title "Graphora"), `frontend/src/main.tsx`, `frontend/src/App.tsx` (renders "graphora"),
  dependencies per plan.md Technical Context (including dev dependencies `fake-indexeddb` and `fflate`); run `npm install` to create `frontend/package-lock.json`. Add
  `frontend/node_modules/`, `frontend/test-results/`, `frontend/playwright-report/` to `.gitignore` (root `dist/` is
  already ignored; do NOT ignore `node_modules/` globally, fixtures contain them on purpose).
- [X] T002 [P] Configure TypeScript strict in `frontend/tsconfig.json` (+ `tsconfig.node.json`): `strict`,
  `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, path alias `@/` → `src/`.
- [X] T003 [P] Configure linting in `frontend/eslint.config.js` (flat config): typescript-eslint strict, react,
  react-hooks, import order; errors for `react/no-danger`, `no-eval`, `no-implied-eval`, `no-new-func`;
  `no-restricted-properties` banning Cytoscape traversal calls `bfs`, `dfs`, `dijkstra`, `aStar`, `floydWarshall`,
  `predecessors`, `successors`, `kruskal`, `pageRank`, `degreeCentrality*`, `closenessCentrality*`,
  `betweennessCentrality` (research R2, R12); `frontend/.prettierrc` (printWidth 120).
- [X] T004 [P] Configure `frontend/vite.config.ts`: React plugin, alias `@`, dev server port 5173 with proxy
  `/api` → `http://127.0.0.1:8000` (no path rewrite, `changeOrigin: false`), build `outDir: dist`, Vitest
  `environment: jsdom`, `setupFiles: ./tests/setup.ts`; create `frontend/tests/setup.ts` (Testing Library jest-dom,
  MSW server start/reset/close).
- [X] T005 [P] Configure `frontend/playwright.config.ts`: Chromium only, `baseURL` `http://127.0.0.1:8765`,
  `webServer` = `cd ../backend && uv run python tests/e2e_server.py --port 8765` (reuse when running), `testDir:
  tests/e2e`, traces on first retry.
- [X] T006 [P] Add to `Makefile`: `web` (`cd frontend && npm run dev`), `web-build` (`cd frontend && npm ci && npm run
  build`), `web-test` (`cd frontend && npm run lint && npm run typecheck && npm test`), `e2e` (`cd frontend && npm run
  build && npx playwright test`); add them to `.PHONY`.
- [X] T007 Add jobs to `.github/workflows/checks.yml`: `frontend` (ubuntu, `actions/setup-node@v4` with Node 22 and npm
  cache on `frontend/package-lock.json`, `npm ci`, `npm run lint`, `npm run typecheck`, `npm run gen:types && git diff
  --exit-code src/api/graph.gen.ts`, `npm test`, `npm run build`), and `e2e` (PostgreSQL 17 service as the backend
  job, setup-uv + `uv sync --locked`, setup-node, `npm ci`, `npx playwright install --with-deps chromium`, `npm run
  build`, `npx playwright test` with `GRAPHORA_TEST_DATABASE_URL`; upload `playwright-report/` on failure).
- [X] T008 [P] Add `gen:types` in `frontend/package.json`: `json2ts -i ../schema/graph.schema.json -o
  src/api/graph.gen.ts --bannerComment "// generated from schema/graph.schema.json by npm run gen:types"`; run it and
  commit `frontend/src/api/graph.gen.ts`.

**Checkpoint**: `make web-test` and `npm run build` pass on an empty app; CI runs the new jobs.

---

## Phase 2: Foundational (backend facts, e2e server, API client, shell)

**Purpose**: everything every screen needs. Components are foundational because every snapshot opens at System level
(clarification Q2).

### Backend: components (FR-021, research R3)

- [X] T009 [P] Write `backend/tests/unit/test_components.py` on small hand-built `GraphDocument`s (like
  `tests/integration/test_query_performance.py` builds one): two dense clusters joined by one link → two components;
  naming rules (common folder; no common folder → most frequent top-level folder, ties by path; root files → `.`;
  duplicates → ` · 2`, ` · 3` in order of first file path); isolated files grouped per top-level folder; ids
  `component:<n>` 1-based in order of first file path; `links` with `imports`, `heuristic`, `in_cycle`, sorted by
  (source, target); `has_cycle`; `include_type_only=False` drops type-only links; externals and unresolved imports
  never in components; the same input twice → same bytes; answer `total` = number of components, `truncated: false`.
- [X] T010 [P] Add hand-written `components` entries to `fixtures/repos/py-cycles/queries.json`,
  `fixtures/repos/ts-app/queries.json` and `fixtures/repos/mixed-fullstack/queries.json` (question `components`, target
  `null`, options `{}`, expected projection: components as `{"name", "files", "has_cycle"}` and links as
  `{"source", "target", "imports", "heuristic", "in_cycle"}`), derived by reading the fixture sources; extend
  `project_answer` in `backend/tests/golden/test_queries.py` to project `components` and `links` that way, and add
  `components` to `_QUESTIONS`.
- [X] T011 Add `Component`, `ComponentLink` to `backend/src/graphora/graph/results.py` (fields of data-model.md),
  `components` and `links` fields on `Answer` (left out of JSON when `None`), `"components"` in `Question`, and text
  lines in `render_text` (`<name>  files <n>  [cycle]`, then `links:` lines `<source name> → <target name>  imports <n>
  [heuristic <h>] [cycle]`).
- [X] T012 Implement `components(ix, *, include_type_only=True) -> Answer` in `backend/src/graphora/graph/queries.py`
  per research R3: undirected weighted file graph from `_links(ix, include_type_only)` file-to-file pairs (weight = edge
  count, both directions summed), nodes and edges added in sorted order, `nx.community.louvain_communities(g,
  weight="weight", resolution=1, seed=0)`, singletons without links regrouped per top-level folder, naming and ids as
  T009, `has_cycle`/`in_cycle` from `cycles(ix, include_type_only=include_type_only)` groups. Check: T009 and
  `tests/golden/test_queries.py` pass; the new `components` entries keep `tests/golden/test_mcp_queries.py` red until
  T014 and `tests/golden/test_http_queries.py` until T015 (expected).
- [X] T013 Add `components` to the CLI: `_QUESTIONS`, no target, rejects `--limit`, `--symbol`, `--max-depth`,
  `--follow-barrels`, `--level` like `overview` does, in `backend/src/graphora/cli/__init__.py`; test in
  `backend/tests/integration/test_query_cli.py` (text and json, usage errors).
- [X] T014 Add MCP tool `components(include_type_only: bool = True)` with a fixed description in `DESCRIPTIONS` to
  `backend/src/graphora/mcp/server.py`; extend `backend/tests/golden/test_mcp_queries.py` `_flags`/CASES so the new
  queries.json entries compare tool = CLI (no `--limit` for `components`, like `projects`); update the tool list
  assertions in `backend/tests/unit/test_mcp_tools.py`.
- [X] T015 Add the row `Question("components", queries.components, None, ("include_type_only",), None)` in
  `backend/src/graphora/api/questions.py`; add `components` to `HTTP` in `backend/tests/golden/test_http_queries.py`,
  to `QUESTION_PATHS` in `backend/tests/integration/test_api.py`, and to `ROUTES`/`PARAMETERS` in
  `backend/tests/integration/test_http_queries_api.py`.

### Backend: line counts, info, UI serving (FR-023, FR-024, FR-025; research R5–R7)

- [X] T016 [P] Write `backend/tests/integration/test_ui_api.py` (`db`): `GET /api/v1/files` returns every stored file
  `{"path", "has_text", "line_count"}` sorted by path and equals `store.get_file(...).line_count` per file; 404 / 409 /
  400 as 018; `GET /api/v1/info` with and without `AskService` and `JobRunner` (`ask.enabled`, `ask.model`
  = the setting or `null`, `jobs.enabled`, `jobs.limits` = the runner's limits (`null` without a runner), `mcp_tools`
  names = the MCP server's store-mode tool names (including `read_lines`) in sorted order); with a UI
  folder (tmp dir with `index.html` and `assets/app.js`): `GET /` → index, `GET /assets/app.js` → file,
  `GET /r/x/y/graph` → index (200), `GET /api/v1/nope` → JSON 404, `GET /../secret` blocked, CSP header on UI responses
  equals contracts/backend.md; without a UI folder `GET /` → JSON 404 as before.
- [X] T017 Add `Store.list_files(repository, snapshot) -> list[tuple[str, bool, int]]` (one `SELECT path, has_text,
  line_count FROM files WHERE repository = %s AND snapshot = %s ORDER BY path`) in
  `backend/src/graphora/store/store.py`, with a test in `backend/tests/golden/test_store_roundtrip.py`.
- [X] T018 Add `GET /api/v1/files` (uses `stored_index` for 404/409, then `list_files`) and `GET /api/v1/info` (no
  parameters; `version` = `importlib.metadata.version("graphora")`; `jobs.limits` from the `JobRunner`'s
  `PipelineLimits` and skipped folder names; tools (store mode, with `read_lines`) from a new constant `TOOL_NAMES` exported by
  `backend/src/graphora/mcp/server.py` with `DESCRIPTIONS`) in `backend/src/graphora/api/routes.py`; `router` takes the
  optional runner and ask service (pass from `create_app`). Paths added to `test_only_read_endpoints`.
- [X] T019 Serve the built UI in `backend/src/graphora/api/__init__.py`: `create_app(..., ui: Path | None = None)`
  mounts, after all API routers, a handler that serves files of `ui` with Starlette `StaticFiles(directory=ui)` and
  returns `ui/index.html` for other `GET` paths not starting with `/api/`; adds the CSP header of contracts/backend.md to
  these responses. In `backend/src/graphora/cli/__init__.py` add `serve --ui DIR` (default `$GRAPHORA_UI_DIR`, else
  `<repo>/frontend/dist` resolved from the package location when it exists). Check: T016 passes.
- [X] T020 Write `backend/tests/e2e_server.py`: `--port`, opens the test database (`GRAPHORA_TEST_DATABASE_URL`), empties
  it, stores the fixtures `py-cycles`, `ts-app`, `mixed-fullstack`, `csharp-multiproject` (via `analyze_fixture` from
  `conftest.py`) and a local git history repository built with `history_repos.make_repo` (for hotspots); starts
  `create_app(store, JobRunner(...), AskService(..., model_factory=<scripted model from tests/unit/scripted_model.py
  with a fixed script answering one impact question>), ui=../frontend/dist)` with uvicorn on 127.0.0.1. Not collected
  by pytest (name does not start with `test_`).

### Frontend: API client, state, shell

- [X] T021 [P] Write `frontend/tests/unit/api.test.ts` (MSW): `apiGet` builds `/api/v1/<path>?<params>` with
  `encodeURIComponent`, parses JSON, turns `{"error": {"kind", "message"}}` bodies into `ApiError` with `status`,
  `kind`, `message`, `retryAfter` (from `Retry-After`); network failure → `ApiError` kind `network`.
- [X] T022 Implement `frontend/src/api/client.ts` (`apiGet`, `apiPost`, `apiUpload`, `ApiError`) and
  `frontend/src/api/types.ts` (hand-written types of Answer, Item, Link, Edge (from `graph.gen.ts`), CycleGroup with
  `suggested_cut`, Component, ComponentLink, Overview, Hotspot fields, Definitions, Job status (stages `queued`,
  `resolving`, `fetching`, `analyzing`, `storing`, `done`, `failed`), Ask step/answer events, Info, Files) per
  contracts of 004/005/010/013/014/018/019. Check: T021 passes.
- [X] T023 Implement `frontend/src/api/queries.ts`: TanStack Query hooks keyed by `[repository, snapshot, question,
  params]` for repositories, graph, overview, components, key_files (limit 500), cycles (limit 500), hotspots (limit
  500), files, info, impact, neighbors, dependencies, dependents, definitions, file lines; `staleTime: Infinity` for
  snapshot data (immutable), retry only on `network`/`store_unavailable`.
- [X] T024 [P] Write `frontend/tests/unit/route.test.tsx`: route state of data-model.md round-trips through the
  address (`/r/:repo/:snap/:screen?level&component&node&impact&hide&path&line`), encoding of `/` and `:` in names, and
  unknown values fall back to defaults (`level=system`); switching to another snapshot clears `node`, `component` and
  `impact` and shows the note "selection cleared: not in this snapshot" when the node does not exist there.
- [X] T025 Implement `frontend/src/routes.tsx` and `frontend/src/state/route.ts` (read/write helpers) with React Router;
  `/` redirects to the last opened snapshot (localStorage key `graphora.last`) or `/import`. Check: T024 passes.
- [X] T026 [P] Write `frontend/src/styles/tokens.css` and `frontend/src/styles/base.css` with the palette and type of
  the mockups (background `#0d1117`-like dark, panel, border, text, muted; accent blue; green resolved/verified; amber
  heuristic/hypothesis; red cycle; component palette of 14 distinct colours), monospace for paths and code.
- [X] T027 [P] Write `frontend/tests/unit/shell.test.tsx`: header shows `repository @ abcdef1` (7 chars, `content:`
  ids shortened to `content:` + 8), one badge per `overview.languages` entry with status analyzed/detected only from
  the overview file counts, model badge `qwen3:8b · local` for `ollama:qwen3:8b`, `agents off` when `ask.enabled` is
  false; sidebar sections and items exactly as FR-001 with the active item marked; footer text.
- [X] T028 Implement `frontend/src/shell/Header.tsx`, `SnapshotPicker.tsx`, `Sidebar.tsx`, `Layout.tsx` and wire them in
  `frontend/src/App.tsx`. Check: T027 passes.
- [X] T029 [P] Write `frontend/tests/unit/errors.test.tsx`: `ErrorState` renders each row of contracts/ui.md § Error and
  empty states with its message and action; `Legend` renders the shared visual language rows.
- [X] T030 Implement `frontend/src/shell/ErrorState.tsx`, `Legend.tsx`, `Loading.tsx`, `Empty.tsx`. Check: T029 passes.
- [X] T031 [P] Write `frontend/tests/unit/hostile.test.tsx`: a shared `Text`/`Path`/`Code` component and every screen
  component written later receive `<script>alert(1)</script>`, `<img src=x onerror=alert(1)>`, `javascript:alert(1)`,
  `**md**` and `[a](javascript:x)` and render them literally (no element created, `textContent` equal to input);
  later phases add their components to this test's table.

**Checkpoint**: backend suite green with components, files, info, UI serving; `make web` shows the shell with a working
snapshot picker against a running `graphora serve`.

---

## Phase 3: User Story 1 - Explore a stored snapshot: graph, impact and code (Priority: P1) 🎯 MVP

**Goal**: System → Component → File graph, side panels, impact mode, code & provenance (§ 2, § 4, § 5).

**Independent Test**: e2e on `py-cycles` and `mixed-fullstack`: open, expand, select, impact, code view; every shown fact
equals the API answer.

- [X] T032 [P] [US1] Write `frontend/tests/unit/graph-elements.test.ts` for `toElements(...)` (pure function): System
  level → one node per component (label `name`, `file_count`) and one edge per component link (width from `imports`,
  class `heuristic` when `heuristic > 0`, class `cycle` when `in_cycle`); Component level → the expanded component's
  files as children, other components collapsed; File level → files and file links from the graph document (classes
  `resolved`/`heuristic`, `type-only`; unresolved imports never become edges; externals only when not hidden);
  `hide=tests` removes paths matching `(^|/)(tests?|__tests__)/|(_test|\.test|\.spec)\.` ; selection and impact classes;
  a snapshot with files but no links and a one-file snapshot give valid elements (no edges, no error).
- [X] T033 [US1] Implement `frontend/src/graph/elements.ts` (`toElements`) and `frontend/src/graph/style.ts`
  (Cytoscape stylesheet from tokens: dashed amber heuristic, red cycle, blue impact, dim others). Check: T032 passes.
- [X] T034 [US1] Implement `frontend/src/graph/GraphView.tsx`: Cytoscape instance, fcose layout (`randomize: false`,
  initial positions on a circle in node-id order so every load gives the same picture), level switch System / Component / File (Symbol tab opens search),
  click component → `level=component&component=…`, click file → `node=…`, filters `hide`, search box placeholder, footer
  breadcrumb "System › <component> (<shown> of <n> files shown)" and the Legend.
- [X] T035 [P] [US1] Write `frontend/tests/unit/side-panel.test.tsx`: component panel (name, file count, lines of code =
  sum of `/files` line counts of its files, depends on / used by counts from component links, centrality rank from
  key_files order, key files list, issues from cycles groups intersecting it, "Expand component", "Ask about <name>");
  file panel (path, lines, hotspot rank if present, dependencies and dependents lists with confidence badges, cycles it
  is in, "Open code", impact toggle).
- [X] T036 [US1] Implement `frontend/src/graph/SidePanel.tsx`, `ComponentPanel.tsx`, `FilePanel.tsx`. Check: T035
  passes.
- [X] T037 [P] [US1] Write `frontend/tests/unit/impact.test.tsx`: impact panel shows `total` from the answer, a bar per
  component with the count of impact items whose file is in it, the heuristic part as "~N heuristic" (items with
  `confidence: "heuristic"`), "and N more" when `truncated`; highlighted node ids equal the answer's item nodes.
- [ ] T038 [US1] Implement `frontend/src/graph/ImpactPanel.tsx` and impact highlighting in `GraphView.tsx` (`impact=on`
  in the address; request `/impact?target=<node>&limit=500`); collapsed component nodes show a badge with the number
  of impact items inside them, and only files of expanded components are highlighted one by one. Check: T037 passes
  (add the badge case to T037).
- [ ] T039 [P] [US1] Write `frontend/tests/unit/code-view.test.tsx`: `FileTree` from the graph document's coverage
  files (folders collapsible, `detected only`/`not code` marked); `CodeView` renders `/file` lines as text with line
  numbers, binary/long/missing states; lines with outgoing edges get markers by type (resolved import, external, HTTP
  route, call reference); selecting a line shows `ProvenancePanel` with type and symbol, `source path:line@short
  commit`, confidence badge, `extractor@version`, snippet hash; outgoing and incoming lists from `/dependencies` and
  `/dependents` with confidence badges and, for heuristic incoming, the matched call/route text from the edge.
- [ ] T040 [US1] Implement `frontend/src/code/CodePage.tsx`, `FileTree.tsx`, `CodeView.tsx`, `ProvenancePanel.tsx`,
  `tokens.ts` (Shiki `codeToTokens` with `createJavaScriptRegexEngine()`, no WASM engine; languages python, typescript, tsx, javascript, csharp loaded lazily; tokens
  rendered as `<span>` text only; fall back to plain text on failure). Check: T039 passes; add these components to
  T031's table.
- [ ] T041 [US1] Write `frontend/tests/e2e/us1-graph.spec.ts`: open `/`, pick `py-cycles`; System level shows the
  components of `/api/v1/components`; expand one; select `loop/a.py`; impact highlights exactly the `/api/v1/impact`
  nodes; open code; click line 1; provenance equals the edge of the graph document; reload the address → same view.
  Same flow on `mixed-fullstack` checks a heuristic link is dashed (has class `heuristic`).

**Checkpoint**: MVP — the graph, impact and code screens work on stored fixtures.

---

## Phase 4: User Story 2 - Import a repository and follow the analysis (Priority: P1)

**Goal**: § 1 Import with GitHub URL and ZIP, stages, limits, coverage, open graph.

**Independent Test**: e2e uploads a fixture ZIP and opens its graph; a failing job shows its reason.

- [ ] T042 [P] [US2] Write `frontend/tests/unit/import.test.tsx` (MSW): GitHub URL + optional ref → `POST /jobs`
  `{"github", "ref"}`; ZIP drop/choose → `POST /jobs/zip?name=<file name>` with the bytes; polling `GET /jobs/{id}`
  every 1 s shows stages in order (`queued`, `resolving`, `fetching`, `analyzing`, `storing`, `done`) with the current
  one active; `done` shows the pinned commit, coverage table (language, files, share bar, depth full / detected only /
  not code from `/overview`) and "Open graph"; `failed` shows the failure kind and message and "Try again"; 429
  `too_many_jobs` message; safety limits panel shows `/info` `jobs.limits` (size, files, time, skipped folders) and
  "never — static analysis only", and no limit numbers when `jobs.limits` is `null`; a job answered at once with `done`
  (reused analysis, FR-013) shows "Open graph" without a progress phase.
- [ ] T043 [US2] Implement `frontend/src/import/ImportPage.tsx`, `SourceForm.tsx`, `ZipDrop.tsx`, `JobProgress.tsx`,
  `Coverage.tsx`, `Limits.tsx`. Check: T042 passes.
- [ ] T044 [US2] Write `frontend/tests/e2e/us2-import.spec.ts`: upload `fixtures` ZIP built in the test from
  `fixtures/repos/py-flat/repo` (Playwright `setInputFiles` with a buffer zipped by a small helper), follow to `done`,
  "Open graph" lands on the System level of the new snapshot; upload a non-ZIP file → failed with its reason; empty
  store → `/` opens Import with the explanation.

**Checkpoint**: import → graph works end to end.

---

## Phase 5: User Story 3 - Insights: cycles with suggested cut, hotspots, search (Priority: P2)

**Goal**: § 8 Cycles with the backend cut suggestion, § 9 Hotspots treemap and table, search.

**Independent Test**: on `py-cycles` and the e2e git repository, cycles, cut, hotspots and search equal the API answers.

### Backend: suggested cut (FR-022, research R4)

- [ ] T045 [P] [US3] Write `backend/tests/unit/test_cycle_cut.py` on hand-built graphs: a 2-file loop → one link,
  `exact`; a triangle → the link with the fewest import edges, ties by (source, target); two loops sharing one link →
  that single link; a self-import → the self link; a group of 21 files → `greedy`; an exact search that exceeds the
  budget (monkeypatch the budget to 1) → `greedy`; removing `suggested_cut.links` always leaves the group acyclic;
  same input twice → same bytes; `level="project"` groups have no `suggested_cut`.
- [ ] T046 [P] [US3] Add hand-written `suggested_cut` to every file-level `cycles` entry (not those with
  `"level": "project"`) of `fixtures/repos/*/queries.json` (as
  `{"method", "links": ["<source path>:<line> -> <target path>", …]}`) and project it in `project_answer` of
  `backend/tests/golden/test_queries.py`; extend `test_cited_edges_are_graph_edges_and_chains_connect` to check cut
  edges are graph edges.
- [ ] T047 [US3] Add `CycleCut` and `CycleGroup.suggested_cut` (JSON `suggested_cut`, text line `suggested cut
  (<method>): <source>:<line> → <target>, …`) in `backend/src/graphora/graph/results.py`; implement the exact search
  (budget constant `CUT_BUDGET = 200_000` acyclicity checks, groups ≤ 20 files) and the greedy rule in
  `backend/src/graphora/graph/queries.py` per research R4; call it for file-level groups in `cycles`. Check: T045, T046,
  MCP and HTTP golden tests pass (update expected text in `backend/tests/unit/test_mcp_tools.py` if it prints cycles).

### Frontend

- [ ] T048 [P] [US3] Write `frontend/tests/unit/cycles.test.tsx`: list of groups (title from first two folder names
  joined with ⇄ or →, files, "<n> edges" = cycle length, type-only mark), header pill "<groups> cycles · <files>
  modules"; selected group shows Before (the cycle links, the cut links red dashed with `path:line`) and After
  (the cycle without the cut links), "Edge to remove" card with source → target, method ("minimum feedback arc set"
  for `exact`, "greedy" otherwise), the import line text from `/file`, "Recommendation only — Graphora never modifies
  your code", "Ask agents about this" prefilled "How do I break the <a> ⇄ <b> cycle?"; "no cycles" empty state.
- [ ] T049 [US3] Implement `frontend/src/insights/CyclesPage.tsx`, `CycleList.tsx`, `CycleDiagram.tsx` (small
  Cytoscape, preset positions), `CutCard.tsx`. Check: T048 passes.
- [ ] T050 [P] [US3] Write `frontend/tests/unit/hotspots.test.tsx`: treemap tiles = hotspot items, area ∝ line count
  from `/files` (minimum area for 0-line files), colour from score normalised to the answer's maximum (low green →
  amber → red), label path and score; "Top risks" table: file, commits, used by (`transitive_dependents`), bus factor
  (`authors`, red when 1, amber when 2) — no names; history base line from the answer's `history` (window start,
  commits read, partial note, local changes note); `not_available` → "history not available (<reason>)" and no tiles.
- [ ] T051 [US3] Implement `frontend/src/insights/HotspotsPage.tsx`, `Treemap.tsx` (`d3-hierarchy` `treemap` with
  `treemapSquarify`, sorted by score then path), `TopRisks.tsx`. Check: T050 passes.
- [ ] T052 [P] [US3] Write `frontend/tests/unit/search.test.tsx`: the search box lists file paths from the graph
  document containing the text (case-insensitive, max 20, sorted) and, for an identifier-like text, `/definitions`
  results (path, line, kind, full name); choosing one selects the file in the graph (`node=`); "no definitions" for an
  empty answer.
- [ ] T053 [US3] Implement `frontend/src/graph/Search.tsx` and wire it into the graph toolbar. Check: T052 passes.
- [ ] T054 [US3] Write `frontend/tests/e2e/us3-insights.spec.ts`: Cycles on `py-cycles` lists the groups of
  `/api/v1/cycles` with their cut; Hotspots on the e2e git repository shows tiles and the table equal to
  `/api/v1/hotspots`; on `py-cycles` (no git) "history not available"; search for a known class opens its file.

**Checkpoint**: insights screens work.

---

## Phase 6: User Story 4 - Ask agents and follow the trace (Priority: P2)

**Goal**: § 6 Ask agents with live steps and § 7 Agent trace; history kept in the browser (clarification Q4).

**Independent Test**: e2e with the scripted model: ask, watch steps, see facts/hypotheses, reload, open the trace.

- [ ] T055 [P] [US4] Write `frontend/tests/unit/sse.test.ts`: the parser handles `event:`/`id:`/`data:` lines,
  multi-line `data`, `\r\n`, chunks split mid-line and mid-UTF-8 character, comments (`:`), and yields `{event, id,
  data}`; `streamAsk` posts `{"repository", "snapshot", "question"}`, yields `step` events, resolves on `answer`, rejects
  on `error` events and on 429/503 bodies (`ApiError`), and stops on abort.
- [ ] T056 [US4] Implement `frontend/src/api/sse.ts` (`parseEvents`, `streamAsk`). Check: T055 passes.
- [ ] T057 [P] [US4] Write `frontend/tests/unit/history.test.ts` (`fake-indexeddb`): `saveRun` keeps the newest 20 per
  (repository, snapshot) and drops older ones; other snapshots untouched; `listRuns` newest first; `clearRuns` removes
  one snapshot's runs; unavailable IndexedDB → in-memory fallback with `persistent: false`.
- [ ] T058 [US4] Implement `frontend/src/agents/history.ts` with `idb` (database `graphora`, store `answers`, key
  `[repository, snapshot, created]`). Check: T057 passes.
- [ ] T059 [P] [US4] Write `frontend/tests/unit/ask.test.tsx`: question box and suggested questions; while streaming,
  steps appear as they arrive with role colours (explorer purple, analyst blue, reviewer amber); the answer shows role
  chips, run stats (tool calls, seconds, model), facts with green checks and citations `path:line` + short commit,
  cycle warnings red, hypotheses amber "Hypothesis — … Not statically proven."; agent text rendered as text (added to
  T031's table); "Highlighted on graph" mini graph of the cited files with links between them from `/neighbors`;
  clicking a node opens it in the main graph; busy (429) and model unavailable (503) states with Retry; history list of
  earlier runs with "Clear history"; "history will not be kept" note when not persistent.
- [ ] T060 [US4] Implement `frontend/src/agents/AskPage.tsx`, `StepList.tsx`, `AnswerCard.tsx`, `CitedGraph.tsx`,
  `RunHistory.tsx`. Check: T059 passes.
- [ ] T061 [P] [US4] Write `frontend/tests/unit/trace.test.tsx`: for a stored run, the timeline lists each trace event
  with role, tool and arguments, result summary, duration when present; revision requests shown as red notes; "Agent
  flow" Explorer → Analyst → Reviewer with the revision loop when revisions > 0; claims table with statuses
  (verified green, rejected red, hypothesis amber); budget bars "Tool calls n / limit" and "Revisions n / limit" from
  the trace; model, duration and tokens chips only when present; empty state links to Ask agents.
- [ ] T062 [US4] Implement `frontend/src/agents/TracePage.tsx`, `Timeline.tsx`, `AgentFlow.tsx`, `ClaimsTable.tsx`,
  `Budget.tsx`. Check: T061 passes.
- [ ] T063 [US4] Write `frontend/tests/e2e/us4-agents.spec.ts` (scripted model of `tests/e2e_server.py`): ask the
  scripted question on `py-cycles`, steps stream in, the answer shows its verified facts and hypothesis, reload keeps
  it in history, Agent trace shows the same steps and claims; a second ask while one runs shows "busy".

**Checkpoint**: agents screens work without a real model.

---

## Phase 7: User Story 5 - Large repositories stay readable (Priority: P3)

**Goal**: § 3 overview and § 4 zoom on 5,000 files within SC-003.

**Independent Test**: e2e on a stored 5,000-file graph: overview < 5 s, expand and impact < 1 s.

- [ ] T064 [P] [US5] Write `backend/tests/integration/test_components_performance.py` (`slow`): `components` on the
  5,000-file graph of `test_query_performance.py` in < 2 s and `cycles` with cuts in < 2 s.
- [ ] T065 [US5] Optimise `components`/cut in `backend/src/graphora/graph/queries.py` only if T064 fails (cache the
  undirected graph on `GraphIndex` like `_runtime_links`).
- [ ] T066 [US5] Add the large-repository panel (files, edges, components, cycles counts from overview / components /
  cycles; "How it stays readable" and legend: node size = dependents, hotspot marker, red bundle = cycle) to
  `frontend/src/graph/OverviewPanel.tsx`, shown on System level; node size from component dependents (sum of incoming
  component link imports) and hotspot markers from `/hotspots` items.
- [ ] T067 [US5] Implement File-level rendering for big snapshots in `frontend/src/graph/GraphView.tsx`: Cytoscape WebGL
  renderer when more than 1,000 nodes, labels hidden below zoom 0.8, `haystack` edges; layout in
  `frontend/src/graph/layout.worker.ts` (fcose headless in a Web Worker) when more than 500 nodes, positions cached per
  (snapshot, level, component).
- [ ] T068 [P] [US5] Implement `frontend/src/graph/Minimap.tsx` (second, non-interactive Cytoscape on the same
  elements, viewport rectangle; dragging the rectangle pans the main view) and "Export SVG"/"Export PNG" in the graph
  toolbar (`cytoscape-svg`, `cy.png`).
- [ ] T069 [US5] Add to `backend/tests/e2e_server.py` the 5,000-file graph stored as repository `large` (same builder
  as `test_query_performance.py`, contents `b"x = 1\n"`), and write `frontend/tests/e2e/us5-large.spec.ts`: overview
  of `large` visible in < 5 s; expanding a component and toggling impact each < 1 s (measured with `performance.now()`
  around the action and a `data-ready` attribute set after layout); with impact on, collapsed components show their
  impact count badge; minimap drag pans the view.

**Checkpoint**: large graphs meet SC-003.

---

## Phase 8: User Story 6 - MCP page and placeholders (Priority: P3)

- [ ] T070 [P] [US6] Write `frontend/tests/unit/mcp.test.tsx`: Claude Code command `claude mcp add graphora -- uv run
  --directory <backend dir placeholder> graphora mcp --repository <repo> --snapshot <snap>` and Cursor JSON with the
  open repository and snapshot, copy buttons; tools table = `/info` `mcp_tools` (name, description), all marked
  read-only; "server: stdio" note; no benchmark numbers; PR impact and Security pages show "not available in this
  version" and contain no digits.
- [ ] T071 [US6] Implement `frontend/src/integrations/McpPage.tsx` and `NotAvailable.tsx`; routes `pr-impact`,
  `security`, `mcp`. Check: T070 passes.
- [ ] T072 [US6] Write `frontend/tests/e2e/us6-mcp.spec.ts`: MCP page lists the tools of `/api/v1/info`; PR impact and
  Security show the placeholder.

---

## Phase 9: Polish & cross-cutting

- [ ] T073 [P] Write `frontend/tests/e2e/errors.spec.ts`: service stopped → "Graphora service unavailable" + Retry;
  unknown snapshot address → "Snapshot not found"; a `stale` analysis (schema version lowered in the test database by
  `e2e_server.py --stale` repository) → "analyze again".
- [ ] T074 [P] Write `frontend/tests/e2e/hostile.spec.ts` (SC-004): `e2e_server.py` stores a hand-built analysis whose
  file names, contents and symbol names contain the T031 strings and a scripted answer quoting them; every screen shows
  them literally and no dialog opens (`page.on("dialog")` fails the test).
- [ ] T075 [P] Add a "Web UI" section to `README.md` (develop with `make web`, demo with `make web-build` + `graphora
  serve`, tests) and to `CLAUDE.md` Commands (`make web`, `make web-build`, `make web-test`, `make e2e`, `serve --ui`,
  `query … components`).
- [ ] T076 Run `specs/019-frontend/quickstart.md` by hand (dev and demo modes) and compare each screen with its mockup
  in `docs/demo/`; note deliberate differences (Assumptions of spec.md) in the PR description; time the SC-001 path
  (empty screen → impact of a file of an imported fixture) and record it (target < 2 min).
- [ ] T077 Run the full suites: `cd backend && uv run pytest -m "not llm"`, `uv run pytest -m slow`, `make web-test`,
  `make e2e`; then mark the PR ready for review and retarget it to `main` if #39 is merged.

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → stories → Phase 9.
- Phase 2: backend tasks T009–T020 and frontend tasks T021–T031 are independent of each other; T020 (e2e server) needs
  T019; frontend shell (T028) needs the client (T022–T023).
- US1 needs Phase 2. US2, US3, US4, US6 need only Phase 2 and can follow in any order; US5 extends US1's `GraphView`.
- Within a story: tests → implementation; backend tasks of a story before its frontend screen that shows them (T045–T047
  before T048).

## Parallel Examples

- Phase 1: T002, T003, T004, T005, T006, T008 together after T001.
- Phase 2: T009 + T010 + T016 + T021 + T024 + T026 + T027 + T029 + T031 (all test or style files).
- US1: T032 + T035 + T037 + T039 tests together; then their implementations.
- US3: T045 + T046 (backend tests) with T048 + T050 + T052 (frontend tests).
- US4: T055 + T057 + T059 + T061.

## Implementation Strategy

- **MVP** = Phases 1–3: shell + graph + impact + code on stored snapshots; push and let Ulyana look at the draft PR.
- Then US2 (import), US3 (insights + cut backend), US4 (agents), US5 (large graphs), US6 (MCP), Polish.
- After every phase: all tests green, push, short Russian summary to Anna before continuing.
