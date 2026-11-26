---

description: "Task list for 018-http-queries"
---

# Tasks: Graph Queries over HTTP

**Input**: Design documents from `specs/018-http-queries/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R8), data-model.md, contracts/http-api.md, quickstart.md

**Tests**: Required (constitution VIII, spec SC-001). Within each phase, write the tests first and confirm they fail.
Expected HTTP bodies are never written by hand: they are the bytes of `graphora query … --format json` (via
`run_query` in `backend/tests/conftest.py`) for the same stored graph and options.

**Organization**: Phase 2 (shared store helper, parameter parsing, route registration from the question table)
blocks every story. Then:

- US1 (P1): `dependencies`, `dependents`, `impact`, `neighbors` (MVP);
- US2 (P1): `cycles`, `key_files`, `overview`, `projects`;
- US3 (P2): `definitions`;
- US4 (P2): the full error table and `stale`.

Paths are relative to the repository root. Code lives in `backend/src/graphora/`, tests in `backend/tests/`. Run
commands from `backend/`. Tests that store analyses are marked `db` (need `make db` and
`GRAPHORA_TEST_DATABASE_URL`). Keep comments minimal, in the style of the existing modules (one short module
docstring with a spec reference, one-line docstrings only where not obvious).

**Commits**: one commit after every task (a test task is committed on its own, before its implementation).
Messages are short, lowercase and English. Push at the end of each phase.

## Phase 1: Setup

- [X] T001 Create `backend/src/graphora/api/questions.py` with a one-line module docstring referencing
  `specs/018-http-queries/contracts/http-api.md`, a frozen dataclass `Question` with the fields of data-model.md
  (`name: str`, `ask: Callable`, `target: str | None` — `"target"`, `"name"` or None —, `options: tuple[str, ...]`,
  `default_limit: int | None`), `QUESTIONS: tuple[Question, ...] = ()`, `DEFAULT_LIMIT, MAX_LIMIT = 50, 500`, and
  `router(store: Store) -> APIRouter` with prefix `/api/v1` that registers nothing yet. Include it in
  `create_app` in `backend/src/graphora/api/__init__.py` right after `router(store)`, and add the 018 contract to
  that module's docstring. Check: `uv run pytest -m "not db and not slow"` passes unchanged.

---

## Phase 2: Foundational (store helper, parameters, registration)

**Purpose**: everything a row of `QUESTIONS` needs to become a working route (research R2–R5, R7).

- [ ] T002 In `backend/src/graphora/api/routes.py` add `stored_index(store, repository, snapshot) -> GraphIndex`
  (research R4): `store.get_analysis`; `None` → `raise _missing(store, repository, snapshot)`; `schema_version !=
  SCHEMA_VERSION` → `ApiError("stale", 409, "<repository> <snapshot> was analyzed with graph schema <n>; analyze
  it again")` (the exact message `/hotspots` gives today); otherwise `queries.index(loads(stored.graph))`. Change
  the `/hotspots` handler to call it, keeping its parameter checks before the store read. Check:
  `uv run pytest tests/integration/test_hotspots_api.py tests/integration/test_api.py` passes unchanged (db).
- [ ] T003 [P] Write `backend/tests/unit/test_api_questions.py` for the functions of T004, without a store
  (build a fake `Question` row and a parameter dict):
  - `_allowed(row)` = (`repository`, `snapshot`, the row's target parameter) required, and the row's `options` plus
    `limit` when `default_limit` is not None optional (unknown and repeated keys are rejected by `_params`, tested
    through the routes in T016);
  - booleans: `"true"`/`"false"` only (`"1"`, `"yes"`, `"True"` → 400); defaults `include_type_only=True`,
    `follow_barrels=False`;
  - integers: `limit`, `max_depth` must match `_INT`; `"x"`, `"1.5"`, `"9999999999"` → 400;
  - `limit` "0..500": `-1` and `501` → 400 `limit must be between 0 and 500`; absent → the row's `default_limit`;
  - `level`: `file` (default) or `project`, anything else → 400;
  - `symbol`: absent → `None`;
  - the returned kwargs contain only the row's options (plus `limit`), so a row without `level` never passes
    `level`.
- [ ] T004 Implement in `backend/src/graphora/api/questions.py`:
  - `_allowed(row) -> tuple[tuple[str, ...], tuple[str, ...]]` (required, optional) for `_params`;
  - `_arguments(row, params) -> tuple[tuple[str, ...], dict]` (positional target, keyword options) per research R2
    and data-model.md § Option kinds, reusing `_params` and `_INT` from `api/routes.py`;
  - `_answer(store, row, request)`: `_params(request, required, optional)` → `_arguments` → `stored_index` →
    `row.ask(ix, *target, **kwargs)`; `NodeNotFound` with `status == "invalid_path"` → `bad_request(exc.message)`,
    other `NodeNotFound` → `not_found(exc.message)`, `ValueError` → `bad_request(str(exc))`; success →
    `Response(dumps(answer), media_type="application/json")` with `results.dumps`;
  - `_openapi(row)`: the `parameters` list for `openapi_extra` (research R7): `repository`, `snapshot`, the target
    parameter (required strings), and each option with its type, default, `enum: ["file", "project"]` for `level`,
    `minimum: 0, maximum: 500` and the row default for `limit`, `minimum: 1` for `max_depth`;
  - in `router`, a loop over `QUESTIONS` (sorted by name) that registers `GET /<name>` with
    `openapi_extra={"parameters": _openapi(row)}`, binding `row` correctly (a factory function, not a late-bound
    closure).
  Check: T003 passes.

**Checkpoint**: an empty table still serves the old API; adding a row is enough to add a route.

---

## Phase 3: User Story 1 - Impact and neighbours of a selected file (Priority: P1) 🎯 MVP

**Goal**: `/api/v1/dependencies`, `/dependents`, `/impact`, `/neighbors` answer exactly as the CLI.

**Independent Test**: store a fixture, request each question for a known file, compare with the CLI bytes.

- [ ] T005 [P] [US1] Write `backend/tests/golden/test_http_queries.py` (`pytestmark = pytest.mark.db`):
  - `CASES` from every `fixtures/repos/*/queries.json` entry, as in `tests/golden/test_mcp_queries.py`, filtered to
    `HTTP = {"dependencies", "dependents", "impact", "neighbors"}` (later phases extend the set);
  - a module-level cache of `analyze_fixture(name)` per fixture, so each fixture is analyzed once;
  - per case: `store.put(name, analysis)`, `TestClient(create_app(store))`, GET `/api/v1/<question>` with
    `repository=name`, `snapshot=analysis.doc.snapshot`, the target (`target=`), `limit=500` unless the entry sets
    one, and the entry's options written as `true`/`false`/numbers/strings;
  - the expected bytes: write `analysis.doc` with `serialize.dumps` to `tmp_path / "g.json"` and run
    `run_query(graph, question.replace("_", "-"), *target, *_flags(options), "--format", "json")` with the same
    `_flags` helper as the MCP golden test (copy it);
  - assert status 200, `content-type` `application/json`, `response.content == as_json`, and a second request gives
    the same bytes (SC-001, SC-002).
- [ ] T006 [P] [US1] Write `backend/tests/integration/test_http_queries_api.py` (`db`), US1 part, on the `ts-app` and
  `py-cycles` fixtures:
  - default limit 50 shows in `options.limit`; `limit=0` gives no items with the real `total` and
    `truncated: true`; `limit=1` on a file with ≥ 2 dependents gives one item and `truncated: true`;
  - `./src/util.ts`, `src/util.ts/` and `file:src/util.ts` give the same body as `src/util.ts`;
  - `target=nope.ts` → 404 `not_found` whose message is the query layer's (`… is not in snapshot …`);
    `target=node_modules/x.js` on `ts-app` → 404 with the reason `excluded_dir`; `target=../x`,
    `target=/etc/passwd`, `target=a\\b` → 400 `bad_request`;
  - `dependents` with `symbol`, `impact` with `max_depth=1` and `follow_barrels=true`, and `level=project` on
    `csharp-multiproject` equal the CLI bytes.
- [ ] T007 [US1] Add the four rows to `QUESTIONS` in `backend/src/graphora/api/questions.py`:
  `dependencies` (target `target`, options `include_type_only`, `level`, default 50), `dependents` (`target`;
  `symbol`, `include_type_only`, `follow_barrels`, `level`; 50), `impact` (`target`; `max_depth`,
  `include_type_only`, `follow_barrels`, `level`; 50), `neighbors` (`target`; `include_type_only`; 50). Check: T005,
  T006 pass.
- [ ] T008 [US1] In `backend/tests/integration/test_api.py`, extend `test_only_read_endpoints` with
  `/api/v1/dependencies`, `/api/v1/dependents`, `/api/v1/impact`, `/api/v1/neighbors` (`["get"]`), and add them to
  the `path` list of `test_only_get` (405 for other methods).

**Checkpoint**: impact mode and the side panel can be served (spec US1).

---

## Phase 4: User Story 2 - Whole-snapshot answers (Priority: P1)

**Goal**: `/api/v1/cycles`, `/key_files`, `/overview`, `/projects` answer exactly as the CLI.

**Independent Test**: for each fixture, compare these four answers with the CLI bytes.

- [ ] T009 [P] [US2] In `backend/tests/golden/test_http_queries.py`, extend `HTTP` with `cycles`, `key_files`,
  `projects` (no `limit` for `projects`, as in the MCP golden test), and add `test_overview` parametrized over every
  fixture: GET `/api/v1/overview` equals `run_query(graph, "overview", "--format", "json")` bytes, twice.
- [ ] T010 [P] [US2] In `backend/tests/integration/test_http_queries_api.py` add: `key_files` default limit 10;
  `projects` on `ts-app` is 200 with an empty project list (not an error); `overview` and `projects` reject
  `limit` and `include_type_only` with 400; `cycles` on `py-cycles` with `include_type_only=false` equals the CLI
  `--no-type-only` bytes.
- [ ] T011 [US2] Add the rows `cycles` (no target; `include_type_only`, `level`; 50), `key_files` (no target;
  `include_type_only`; 10), `overview` (no target, no options, `default_limit=None`, ask `queries.overview`),
  `projects` (no target, no options, `default_limit=None`, ask `queries.projects`) in
  `backend/src/graphora/api/questions.py`. Check: T009, T010 pass.
- [ ] T012 [US2] Add the four paths to `test_only_read_endpoints` and `test_only_get` in
  `backend/tests/integration/test_api.py`.

**Checkpoint**: the cycles screen and the header numbers can be served (spec US2).

---

## Phase 5: User Story 3 - Find a symbol by name (Priority: P2)

**Goal**: `/api/v1/definitions?name=…` lists exact-name definitions as the CLI.

**Independent Test**: a known class name and an unknown name on a fixture, compared with the CLI.

- [ ] T013 [P] [US3] In `backend/tests/golden/test_http_queries.py` add `test_definitions` over the fixtures that
  have hand-written `definitions` in `expected.json` (the `DEFINED` list of the MCP golden test): for each short name
  found there, GET `/api/v1/definitions?name=<n>&limit=500` equals `run_query(graph, "definitions", n, "--limit",
  "500", "--format", "json")`.
- [ ] T014 [P] [US3] In `backend/tests/integration/test_http_queries_api.py` add: an unknown name gives 200 with no
  items (not 404); `name` missing or empty → 400; `target=` instead of `name=` → 400 `unknown parameter: target`;
  `include_type_only` → 400.
- [ ] T015 [US3] Add the row `definitions` (target parameter `name`; no options; 50) in
  `backend/src/graphora/api/questions.py`, and its path in `backend/tests/integration/test_api.py`. Check: T013,
  T014 pass.

**Checkpoint**: symbol search can be served (spec US3).

---

## Phase 6: User Story 4 - Clear errors for bad requests and old analyses (Priority: P2)

**Goal**: every invalid request from contracts/http-api.md § Errors gets its status and kind; no hostile echo.

**Independent Test**: the error table as one parametrized test; a stored analysis with an old schema version.

- [ ] T016 [US4] In `backend/tests/integration/test_http_queries_api.py` add `test_errors`, parametrized over
  (route, extra params, status, kind) covering every row of contracts/http-api.md § Errors: unknown parameter,
  repeated parameter (raw URL `…&limit=1&limit=2`), missing `repository`/`snapshot`/`target`, `include_type_only=yes`,
  `limit=x`, `limit=501`, `level=module`, `max_depth=0`, `symbol` on `/cycles`, `max_depth` on `/dependents`,
  `level=project` with `symbol`, `follow_barrels=true` and `include_type_only=false`, an unknown repository, an
  unknown snapshot. Each body is `{"error": {"kind", "message"}}`.
- [ ] T017 [US4] In the same file add `test_stale`: store a fixture analysis, then set its `schema_version` to
  `SCHEMA_VERSION - 1` with SQL on `store._conn` (`UPDATE analyses SET schema_version = …`), and check that every
  one of the nine routes answers 409 `stale`; and `test_no_echo`: a hostile `symbol` / unknown parameter value
  (`<script>…`, a 10 kB string) never appears in the error body (FR-011).
- [ ] T018 [US4] Fix whatever T016–T017 find in `backend/src/graphora/api/questions.py` (expected: nothing beyond
  Phase 2). Check: `uv run pytest tests/integration/test_http_queries_api.py tests/unit/test_api_questions.py`.

**Checkpoint**: all four stories pass on their own.

---

## Phase 7: Polish & cross-cutting

- [ ] T019 [P] Write `backend/tests/integration/test_http_queries_performance.py` (`pytest.mark.slow` and
  `pytest.mark.db`): store the 5,000-file graph built by `_graph()` of `tests/integration/test_query_performance.py`
  (import it; store it as `store.put("perf", Analysis(doc=loads(_graph()), warnings=(), contents={}))` with
  `Analysis` from `graph/build.py`),
  then time one request per route (impact/dependents/dependencies/neighbors on a central file such as
  `pkg00/m0000.py`, definitions with any name) and assert each < 3 s (SC-003).
- [ ] T020 [P] In `backend/tests/integration/test_http_queries_api.py` add `test_openapi`: for each of the nine
  routes, `client.app.openapi()["paths"]` lists exactly the parameters of contracts/http-api.md with the right
  `required` flags, `limit` `minimum` 0 / `maximum` 500 and default, `level` enum; and `test_concurrent`: eight
  threads asking different questions of one snapshot get the same bytes as single requests.
- [ ] T021 [P] Add to `CLAUDE.md`, after the `/hotspots` lines of the analysis store block, one paragraph "Graph
  questions over HTTP (feature 018)" with two `curl` examples (`/api/v1/impact?…&target=<path>` and
  `/api/v1/cycles?…`) and the note that each answer equals `graphora query … --format json`.
- [ ] T022 Run the quickstart (`specs/018-http-queries/quickstart.md`) by hand against `graphora serve`, then the full
  suite `uv run pytest` and `uv run pytest -m slow` (SC-006); mark tasks done.

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → stories. T002 and T003 are independent; T004 needs both.
- US1, US2, US3 only add rows and tests; after Phase 2 they are independent of each other, but they all edit the
  same `QUESTIONS` table and `test_api.py` lists, so do them one after another (P1 order: US1, US2, then US3).
- US4 needs the rows of US1–US3 (the stale test covers all nine routes).
- Polish after US4.

## Parallel Examples

- Phase 2: T002 (`routes.py`) together with T003 (unit test file).
- US1: T005 (golden test) together with T006 (integration test), then T007.
- US2: T009 with T010; US3: T013 with T014.
- Polish: T019, T020, T021 together.

## Implementation Strategy

- **MVP** = Phases 1–3: impact and neighbours over HTTP, enough for the first frontend screen (docs/demo § 4, § 2).
- Then US2 (cycles screen, header), US3 (search), US4 (error table hardening), Polish.
- Each phase ends with its tests green and a push; the PR is reviewed by Ulyana (`api/` is her module).
