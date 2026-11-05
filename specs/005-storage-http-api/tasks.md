---

description: "Task list for 005-storage-http-api"
---

# Tasks: Analysis Storage and HTTP API

**Input**: Design documents from `specs/005-storage-http-api/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R13), data-model.md, contracts/cli.md,
contracts/http-api.md, contracts/store-api.md, quickstart.md

**Tests**: Required. Constitution Principle VIII requires golden coverage of the `graph.build` change and
repeated-run identity; SC-001 … SC-007 are checked by tests. Within each story, write the tests first and
confirm they fail before you implement.

**Organization**: Tasks are grouped by user story:

- US1 (P1): an analysis is kept and reused, not recomputed (store write path, `analyze --store`);
- US2 (P1): read graphs and source files over HTTP (store read path, API, `graphora serve`).

US2's tests fill the store through `Store.put` from US1, so US1 comes first.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: The user story the task belongs to (US1, US2)

Paths are relative to the repository root. Code lives in `backend/src/graphora/`, tests in
`backend/tests/`. Run commands from `backend/`. Do not edit any existing test or `expected.json`
(SC-007). Tests that need PostgreSQL carry `@pytest.mark.db` (research R12).

---

## Phase 1: Setup

**Purpose**: Dependencies, a local PostgreSQL, CI and the test fixture every store test uses.

- [ ] T001 Update `backend/pyproject.toml` (research R1, R8, R9): add runtime dependencies
  `psycopg[binary]`, `fastapi`, `uvicorn`, and move `jsonschema==4.26.0` from the `dev` group to runtime;
  add `httpx` to the `dev` group. Pin each new package to an exact version (`==`) with `uv add`, as for
  tree-sitter, and commit `backend/uv.lock`. Add the marker
  `"db: needs PostgreSQL via GRAPHORA_TEST_DATABASE_URL (deselect with -m 'not db')"` next to `slow`.
- [ ] T002 [P] Create `docker-compose.yml` at the repository root with one service `postgres`: image
  `postgres:17`, port `127.0.0.1:5432:5432` (never `0.0.0.0`), env `POSTGRES_USER=graphora`,
  `POSTGRES_PASSWORD=graphora`, `POSTGRES_DB=graphora`, a named volume for data, and an init script
  `docker/postgres-init.sql` (create it) that runs `CREATE DATABASE graphora_test;`. Add `db` (`docker compose
  up -d --wait postgres`) and `db-down` (`docker compose down`) targets to `Makefile` and to its `.PHONY`
  line.
- [ ] T003 [P] Update `.github/workflows/checks.yml`: add a `services.postgres` block (image `postgres:17`,
  the same user/password, `POSTGRES_DB=graphora_test`, port `5432:5432`, health check `pg_isready`) and set
  `GRAPHORA_TEST_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora_test` on the Test step.
- [ ] T004 Add to `backend/tests/conftest.py` (after T001, research R12):
  - a session fixture `database_url` that returns `os.environ["GRAPHORA_TEST_DATABASE_URL"]`, or calls
    `pytest.fail("GRAPHORA_TEST_DATABASE_URL is not set: run `make db` and export it, or deselect with -m 'not db'")`
    when it is missing — never `pytest.skip`;
  - a fixture `store` that opens `graphora.store.Store.open(database_url)`, runs
    `TRUNCATE files, analyses, blobs` before yielding, and closes it afterwards;
  - a helper `analyze_fixture(name) -> graphora.graph.build.Analysis` that runs `analyze()` on
    `FIXTURES / name / "repo"` with the CLI default limits.
  The existing `_no_network` fixture stays as is: psycopg's libpq connects outside Python's `socket`
  (research R1). Add one `db` test in `backend/tests/integration/test_store.py` that opens the store under
  `_no_network` and proves it connects.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The exact analyzed bytes, the text rules, and an openable store. Both stories need them.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests

- [ ] T005 [P] Create `backend/tests/unit/test_build_analyze.py` (research R4, R6):
  - for every fixture in `fixtures/repos/`, `dumps(analyze(...).doc) == dumps(build(...)[0])` and the warnings
    are equal;
  - `analysis.contents` keys are exactly the `coverage.files` paths without the `unreadable` flag, and each
    value equals the file's bytes on disk;
  - `current_extractors() == analyze(...).doc.extractors` for a Python-only, a TS-only and a mixed fixture.
- [ ] T006 [P] Create `backend/tests/unit/test_store_text.py` for `graphora.store.text` (research R5):
  - `split_lines(b"a\nb\r\nc\rd")` gives `("a", "b", "c", "d")`; a trailing `\n` adds no empty line;
    `b""` gives `()`; `b"\n"` gives `("",)`;
  - `decode("x.py", data)` follows PEP 263: a `# -*- coding: latin-1 -*-` file with byte `0xe9` decodes;
    the same bytes in `x.ts` give `None`; any data containing `b"\x00"` gives `None`; invalid UTF-8 gives
    `None`;
  - a UTF-8 BOM is removed from the first line only;
  - line numbering matches the adapters: for every fixture with an `expected.json`, every expected edge's
    `line` is within `1 … len(text_lines(path, bytes))`, and the served line at that number contains the
    start of the import statement (`import`, `from`, `export`, `require(` or `import(`). Do not assert that
    the line contains the symbol: multi-line imports (`import {\n a\n} from "./x"`, `from x import (\n a)`)
    place the symbol on a later line;
  - add a temp file with lone `\r` line endings (`b"import a\rimport b\r"`), analyze it, and assert the
    edge to `b` has `line == 2` and `text_lines` line 2 is `import b`.

### Implementation

- [ ] T007 In `backend/src/graphora/graph/build.py` add a frozen dataclass `Analysis(doc, warnings, contents)`
  with `contents: Mapping[str, bytes]` (a `types.MappingProxyType`), and a function `analyze(root, max_files,
  max_bytes, deadline, snapshot=None) -> Analysis` holding the current body of `build()`; `contents` is the
  existing local `contents` dict (bytes as read, before decoding). Make `build()` call `analyze()` and return
  `(a.doc, a.warnings)`. Add `current_extractors() -> dict[str, str]` returning the same map `build()` writes
  into `GraphDocument.extractors`, and make `build()` use it so the two cannot drift. Makes T005 pass.
- [ ] T008 [P] Create `backend/src/graphora/store/text.py` (research R5): `split_lines(data: bytes) ->
  tuple[bytes, ...]` splitting on `\r\n`, lone `\r` and `\n`; `decode(path: str, data: bytes) -> str | None`
  using `tokenize.detect_encoding` for paths ending in `.py` and strict UTF-8 otherwise, returning `None` on
  any decode error or a NUL byte; `text_lines(path, data) -> tuple[str, ...] | None` that decodes, splits
  and strips a leading `﻿` from line 1. Reuse the PEP 263 logic from `graph/build.py::_decode` by moving
  it here and importing it in `build.py` (one implementation). Makes T006 pass.
- [ ] T009 Create `backend/src/graphora/store/schema.sql` exactly as in data-model.md § PostgreSQL tables:
  `store_meta(key text PRIMARY KEY, value text NOT NULL)`; `analyses` with `PRIMARY KEY (repository,
  snapshot)` and a `CHECK (snapshot ~ '^([0-9a-f]{40}(\+dirty:[0-9a-f]{16})?|content:[0-9a-f]{16})$')` and
  `CHECK (char_length(repository) BETWEEN 1 AND 300)`; `blobs(sha256 text PRIMARY KEY, content bytea NOT
  NULL)`; `files` with `size bigint NULL` ("NULL when unreadable"), `sha256 text NULL REFERENCES blobs`
  ("NULL when unreadable or has_text = false"), `PRIMARY KEY (repository, snapshot, path)` and
  `FOREIGN KEY (repository, snapshot) REFERENCES analyses ON DELETE CASCADE`. Every statement uses
  `IF NOT EXISTS`; the file ends with `INSERT INTO store_meta VALUES ('store_version', '1') ON CONFLICT DO
  NOTHING`. No timestamps, serials or defaults that depend on time.
- [ ] T010 Create `backend/src/graphora/store/__init__.py` and `backend/src/graphora/store/store.py` with the
  types from data-model.md (`StoredAnalysis`, `FileText`, `StoreResult(action, analysis)` with action
  `"stored" | "replaced" | "reused"`), `class StoreUnavailable(Exception)` with a `reason` attribute, and
  `Store.open(url) -> Store` / `Store.close()` (research R2): connect with `psycopg.connect(url)`, apply
  `schema.sql` (read with `importlib.resources`) in one transaction, then read `store_version`; a value other
  than `"1"` raises `StoreUnavailable("store version N, expected 1")`. Wrap every `psycopg.OperationalError`
  in `StoreUnavailable` whose reason is the error text with any password removed (strip it from the URL with
  `psycopg.conninfo.conninfo_to_dict` before formatting). Add `db` tests to
  `backend/tests/integration/test_store.py`: open twice on the same database (idempotent), wrong
  `store_version` row → `StoreUnavailable`, unreachable URL `postgresql://u:secret@127.0.0.1:1/x` →
  `StoreUnavailable` whose reason does not contain `secret`.

**Checkpoint**: `analyze()` exists, text rules are tested, the store opens.

---

## Phase 3: User Story 1 - An analysis is kept and reused, not recomputed (Priority: P1) 🎯 MVP

**Goal**: `graphora analyze … --store` keeps the graph and file bytes per (repository, snapshot), reuses
them when versions match, never downloads a stored GitHub commit again, and never leaves a partial
analysis.

**Independent Test**: Store every fixture with `--store`, open a new connection, read each graph back and
compare with plain CLI output byte for byte; store a fake GitHub commit twice and see one API request and
one download in total.

### Tests for User Story 1

- [ ] T011 [P] [US1] Add `db` tests to `backend/tests/integration/test_store.py` for `Store.put`,
  `find_reusable`, `get_analysis` (FR-001 … FR-009, contracts/store-api.md):
  - first `put` → `"stored"`; `get_analysis` returns the `dumps(doc)` bytes, `schema_version == 2`,
    `extractors == current_extractors()`, the warnings sorted;
  - second `put` of the same analysis → `"reused"` and no row changes (compare a `SELECT` dump of all three
    tables before and after);
  - update the stored `extractors` column by hand to an older version, `put` again → `"replaced"`, one
    analysis row for the pair, its files match the new analysis;
  - `files` rows equal `coverage.files` paths exactly; skipped entries have no row; an `unreadable` file
    has `size IS NULL`, `sha256 IS NULL`, `has_text = false`; a PNG in a temp project has `has_text =
    false`, a `size`, and no blob;
  - two snapshots that share a file share one `blobs` row;
  - atomicity: monkeypatch the files insert to raise after the analyses insert → nothing visible, and an
    earlier stored analysis of the pair is unchanged (FR-006);
  - concurrency: two threads with two `Store` objects `put` the same pair at once → exactly one analysis
    row, both results name the same pair, one is `"stored"` and the other `"reused"` (FR-009);
  - a document that fails `schema/graph.schema.json` (monkeypatch `dumps` to drop `coverage`) → error and
    nothing stored (R8);
  - restart: close the store, `Store.open` again, every analysis and file is unchanged (FR-010, SC-003);
  - a `contents` map with an extra or missing path → `ValueError`, nothing stored;
  - a temp folder holding only `README.md` → stored with zero nodes and edges and one `files` row
    (`has_text = true`).
- [ ] T012 [P] [US1] Create `backend/tests/integration/test_store_cli.py` with `db` tests via `run_analyze`
  (contracts/cli.md):
  - `--store` on `py-flat`: stdout is byte-identical to a run without `--store`; stderr has
    `graphora: info: stored repo content:<hash>`; a second run prints `reused` and identical stdout;
  - `--store --out f`: `f` is written and equals plain output;
  - GitHub via `FakeGitHub` (as in `tests/integration/test_ingest_cli.py`): first `--store` run makes one
    `api.github.com` and one `codeload.github.com` request; a second run with the same ref makes exactly one
    `api.github.com` request and **no** `codeload.github.com` request, prints `reused github.com/<o>/<r>
    <sha>` and identical stdout (FR-008, SC-002); its stderr has no `fetched` line, and its warning lines and
    `analyzed … files` summary line equal those of the first run (use a fake repository with an invalid
    `tsconfig.json` so there is a warning; contracts/cli.md § stderr on a GitHub reuse);
  - the same ZIP (built with `tests/archives.make_zip`) analyzed twice with `--store` → `stored`, then
    `reused`, identical stdout, one analysis row;
  - store failure after analysis: monkeypatch `Store.put` to raise `StoreUnavailable("boom")` → exit `6`,
    empty stdout, `--out` file not created;
  - interrupt during the store write (SC-006): for a ZIP source, monkeypatch the files insert in `Store.put`
    to raise `KeyboardInterrupt` → exit `130`, no analysis row for the pair, and no new `graphora-*` folder
    in `tempfile.gettempdir()` (compare the listing before and after, as in
    `tests/integration/test_ingest_cleanup.py`);
  - `--store` with no URL anywhere → exit `6`, `graphora: error: store unavailable: …`; unreachable URL →
    exit `6` and the password is not in stderr;
  - `--database x` without `--store` → exit `2`, `graphora: error: --database requires --store`;
  - without `--store`, monkeypatch `psycopg.connect` to raise → a plain run still succeeds (no connection
    attempted).
- [ ] T013 [P] [US1] Create `backend/tests/unit/test_fetch_sha.py` (new file; do not edit existing tests),
  using `FakeGitHub`: `fetch_snapshot(GitHubSource,
  …, sha=<40 hex>)` makes no `api.github.com` request and downloads that SHA; `sha="abc"` → `ValueError`;
  `sha` with a `LocalSource` or `ZipSource` → `ValueError`; `sha=None` behaves as in 002.
- [ ] T014 [P] [US1] Create `backend/tests/golden/test_store_roundtrip.py` (`db`, SC-001): for every fixture,
  store it, read it back with `get_analysis`, and assert the bytes equal `run_analyze(fixture)` stdout; repeat
  the whole loop 3 times on a truncated store and assert all runs equal.

### Implementation for User Story 1

- [ ] T015 [US1] Implement `Store.find_reusable`, `Store.get_analysis` and `Store.put` in
  `backend/src/graphora/store/store.py` (research R3, R6, R7, R8):
  - reusable means `schema_version == SCHEMA_VERSION and extractors == current_extractors()`; `extractors`
    and `warnings` are stored as `json.dumps(..., sort_keys=True, separators=(",", ":"))`;
  - `put(repository, analysis)`: serialize with `dumps`, validate the parsed bytes with `jsonschema` against
    `schema/graph.schema.json`, loaded once from `Path(__file__).resolve().parents[4] / "schema" /
    "graph.schema.json"` (the backend runs from the repository checkout via `uv sync`; packaging the schema
    for a standalone install is 007's concern — say so in the module docstring); check `contents` keys + `unreadable` paths == coverage paths,
    else `ValueError`; a repository name longer than 300 characters → `ValueError("repository name longer
    than 300 characters")` (FR-002) before any database call; then in one transaction: `SELECT pg_advisory_xact_lock(<signed 64-bit int from the
    first 8 bytes of sha256(repository + "\0" + snapshot)>)`, re-check reusable → return `"reused"`; else
    `DELETE` the old analysis (cascade), `INSERT … ON CONFLICT DO NOTHING` the blobs of files whose
    `text_lines()` is not `None`, insert the analysis row, insert file rows with `executemany` in sorted path
    order; return `"stored"` or `"replaced"`;
  - every database error → `StoreUnavailable` (connection) or re-raise (others) after rollback.
  Makes T011 pass.
- [ ] T016 [US1] Add the optional `sha: str | None = None` parameter to `fetch_snapshot` in
  `backend/src/graphora/ingest/fetch.py` (contracts/store-api.md): for a `GitHubSource`, a given `sha` must
  match `^[0-9a-f]{40}$` and replaces the `github.resolve_sha` call; for any other source a non-`None` `sha`
  raises `ValueError`. Update the module docstring. Do not edit
  `specs/002-repo-ingest/contracts/ingest-api.md` (other owner); note the change in the PR description and
  request Anna's review. Makes T013 pass.
- [ ] T017 [US1] Add `--store` and `--database` to `graphora analyze` in
  `backend/src/graphora/cli/__init__.py` (contracts/cli.md, research R13):
  - `EXIT_STORE = 6`; `--database` without `--store` → usage error `--database requires --store`, exit 2;
  - with `--store`: resolve the URL (`--database`, else `GRAPHORA_DATABASE_URL`, else `StoreUnavailable("no
    database URL: use --database or GRAPHORA_DATABASE_URL")`), `Store.open` **before** fetching; for a
    `GitHubSource` call `github.resolve_sha`, then `find_reusable`; on a hit use the stored graph bytes as
    `data` and skip `fetch_snapshot`; otherwise run `fetch_snapshot(..., sha=sha)` and `analyze()` (instead of
    `build()`), `with_skipped`, then `store.put(fetched.repository, analysis_with_skipped)` inside the `with`
    block; `data` is the stored graph bytes;
  - the analysis passed to `put` is `dataclasses.replace(analysis, doc=with_skipped(analysis.doc,
    fetched.skipped))`;
  - log `graphora: info: <action> <repository> <snapshot>` before the summary line; on a GitHub reuse print
    stderr exactly as contracts/cli.md § stderr on a GitHub reuse (stored warnings, summary computed from
    the stored bytes; no `fetched` line);
  - if `put` raises, write nothing to stdout or `--out` and return the matching exit status;
  - `StoreUnavailable` → `graphora: error: store unavailable: <reason>`, exit 6;
  - without `--store`, the code path is the existing one (still `build()`), so no import of `psycopg` happens:
    import `graphora.store` lazily inside the `--store` branch.
  Makes T012 pass. Run T014.

**Checkpoint**: US1 complete: `make check` passes; quickstart step 2 works.

---

## Phase 4: User Story 2 - Read graphs and source files over HTTP (Priority: P1)

**Goal**: A read-only HTTP API lists stored repositories, returns stored graph bytes unchanged, and serves
file text or line ranges only from the store.

**Independent Test**: Fill a store with fixtures via `Store.put`, call every endpoint with FastAPI's
`TestClient`, compare the graph with CLI output and file lines with files on disk, and send hostile paths.

### Tests for User Story 2

- [ ] T018 [P] [US2] Add `db` tests to `backend/tests/integration/test_store.py` for `list_repositories` and
  `get_file` (FR-012, FR-014, FR-015): sorted repositories and snapshots; `get_file` whole file and ranges;
  `end` past the last line is clamped; `start < 1`, `end < start`, `start > line_count` → `ValueError`; a
  `has_text = false` file returns `FileText(has_text=False, line_count=0, start=0, end=0, lines=())` and
  `start`/`end` on it → `ValueError`; empty text file → `line_count 0`, `lines ()`; unknown repository,
  snapshot or path → `None`.
- [ ] T019 [P] [US2] Create `backend/tests/integration/test_api.py` (`db`) using
  `fastapi.testclient.TestClient(create_app(store))` (contracts/http-api.md):
  - `GET /api/v1/repositories` on an empty store → `{"repositories":[]}`; after storing `py-flat`, `ts-app`
    and a second snapshot → sorted names and snapshots, body bytes equal to the contract's compact JSON;
  - `GET /api/v1/graph` → `200`, `application/json`, body bytes == stored bytes == plain CLI output; two
    calls give identical bytes; unknown repository and unknown snapshot → `404`, `kind: not_found`, message
    names which one;
  - a `+dirty:` snapshot: stored from a temp git repo with an uncommitted change; found with `%2B`, not found
    with a raw `+`;
  - `GET /api/v1/file` whole and `start=3&end=5`; the response lines equal the file's lines on disk;
  - hostile paths: `../../etc/passwd`, `/etc/passwd`, `%2e%2e/x`, `src\\a.py`, `./src/a.py`, `SRC/A.PY`, a
    path under a skipped folder (`.venv/...` in `py-flat` if present, else a temp project), and a path of
    another snapshot → `404` each; assert (monkeypatch `builtins.open` and `os.open` to raise during the
    request) that the handler opens no file;
  - missing parameter, unknown parameter, `start=abc`, `start=0` → `400 bad_request`, no FastAPI default
    `detail` body;
  - store failure: monkeypatch the store method to raise `StoreUnavailable` → `503 store_unavailable`;
    an unexpected `RuntimeError("secret /Users/x")` → `500 internal` whose body contains neither `secret` nor
    `/Users`;
  - `POST`, `PUT`, `DELETE` on every path → `405`; no other routes exist besides the three and the OpenAPI
    docs (iterate `app.routes`) (FR-018).
- [ ] T020 [P] [US2] Add to `backend/tests/integration/test_store_cli.py`: `graphora serve` with no database
  URL → exit 6 without listening (call `main(["serve"])` with `uvicorn.run` monkeypatched to fail the test
  if called); `serve` passes `host="127.0.0.1"`, `port=8000` to `uvicorn.run` by default and the given
  values with `--host`/`--port` (FR-020).

### Implementation for User Story 2

- [ ] T021 [US2] Implement `Store.list_repositories` and `Store.get_file` in
  `backend/src/graphora/store/store.py` per contracts/store-api.md and data-model.md § FileText, using
  `text_lines()` on the blob for range slicing; all reads are single `SELECT`s ordered in SQL with `COLLATE
  "C"` so order does not depend on the database locale. Makes T018 pass.
- [ ] T022 [P] [US2] Create `backend/src/graphora/api/errors.py` (research R11): `ApiError(kind, status,
  message)`; `json_bytes(obj) -> bytes` with `json.dumps(obj, sort_keys=True, ensure_ascii=False,
  separators=(",", ":")).encode()`; exception handlers for `ApiError`, `RequestValidationError` (→ `400
  bad_request` naming the parameter, never echoing input), `StoreUnavailable` (→ `503`), and `Exception` (→
  `500 internal`, fixed message `internal error`, details logged with `logging.getLogger("graphora.api")`).
- [ ] T023 [US2] Create `backend/src/graphora/api/routes.py` and `backend/src/graphora/api/__init__.py` with
  `create_app(store: Store) -> FastAPI` (contracts/http-api.md): three `GET` routes under `/api/v1`; reject
  unknown query parameters with `bad_request`; `graph` returns `Response(stored_bytes,
  media_type="application/json")`; `file` maps `None` → `404` naming the missing part (check repository,
  then snapshot, then path) and `ValueError` → `400`; every other body via `json_bytes`. Handlers are plain
  `def` (psycopg is sync; FastAPI runs them in its thread pool). `Store` keeps its single connection and
  guards every public method with a `threading.Lock`, so concurrent requests are serialized (enough for a
  local single-user service; a pool can replace it in 007 without changing the `Store` API). Add the lock
  in `backend/src/graphora/store/store.py` and a test in T019 that 8 concurrent graph requests all return
  the stored bytes. Makes T019 pass.
- [ ] T024 [US2] Add the `serve` subcommand to `backend/src/graphora/cli/__init__.py` (contracts/cli.md):
  `--database`, `--host` (default `127.0.0.1`), `--port` (default `8000`); open the store first (exit 6 on
  `StoreUnavailable`), then `uvicorn.run(create_app(store), host=..., port=...)`; close the store on exit;
  return 0 after `SIGINT`/`SIGTERM`. Makes T020 pass.

**Checkpoint**: US1 and US2 complete; quickstart steps 1–4 work.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T025 [P] Add a `slow` + `db` test `backend/tests/integration/test_store_performance.py` (SC-004): build
  a temp project of 5,000 small Python files (reuse the generator from
  `backend/tests/integration/test_performance.py` if it has one), store it, then assert `GET /api/v1/graph`
  under 2 s and `GET /api/v1/file` with a range under 0.5 s via `TestClient`; and that a second `--store`
  run on a fake GitHub commit finishes under 2 s (SC-002).
- [ ] T026 [P] Check every pre-005 test still passes unchanged with `uv run pytest -m "not db"` and with
  the database (SC-007), and that `git diff main -- backend/tests fixtures` shows only new files plus the
  `conftest.py` additions from T004.
- [ ] T027 Run `make lint` and fix findings in new files; run `quickstart.md` steps 1–6 by hand and record
  the result in the PR description.
- [ ] T028 Open a separate shared-files PR **before this feature's PR is marked ready**, agreed with Anna
  (team-workflow.md § Rules): add to `CLAUDE.md` Commands `make db`, `export GRAPHORA_TEST_DATABASE_URL=…`,
  `uv run pytest -m "not db"`, `analyze … --store`, `graphora serve`; note in `docs/product/team-workflow.md`
  that `make check` needs `make db` from 005 on. Also make the `Makefile` `test` target print a one-line hint
  when `GRAPHORA_TEST_DATABASE_URL` is unset (in this PR; the Makefile is not a shared file).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 first (dependencies); T002, T003 in parallel; T004 after T001.
- **Foundational (Phase 2)**: after Setup. T005/T006 tests first; T007 and T008 in parallel; T009 → T010.
- **US1 (Phase 3)**: after Phase 2. Tests T011–T014 in parallel; then T015, T016 (parallel), then T017.
- **US2 (Phase 4)**: after T015 (tests store data with `put`). T018–T020 in parallel; T021, T022 in
  parallel; T023 after both; T024 after T023.
- **Polish (Phase 5)**: after US2.

### Within Each Story

- Tests are written and seen failing before implementation.
- Store functions before CLI and API code that calls them.
- Commit after each task or logical group.

### Parallel Opportunities

- T002, T003; T005, T006; T007, T008.
- T011, T012, T013, T014; T015 with T016.
- T018, T019, T020; T021 with T022.
- T025, T026.

---

## Parallel Example: User Story 1

```text
Task: "T011 store put/reuse/replace/atomic/concurrent tests in backend/tests/integration/test_store.py"
Task: "T012 analyze --store CLI tests in backend/tests/integration/test_store_cli.py"
Task: "T013 fetch_snapshot sha tests in backend/tests/unit/test_fetch_sha.py"
Task: "T014 golden round trip in backend/tests/golden/test_store_roundtrip.py"
```

## Parallel Example: User Story 2

```text
Task: "T018 list/get_file store tests in backend/tests/integration/test_store.py"
Task: "T019 API tests in backend/tests/integration/test_api.py"
Task: "T020 serve CLI tests in backend/tests/integration/test_store_cli.py"
```

---

## Implementation Strategy

### MVP First

1. Phase 1 and Phase 2.
2. Phase 3 (US1): the store fills and reuses analyses from the CLI.
3. Stop and validate: T014 golden round trip, quickstart step 2. This alone unblocks 006 and 008, which use
   `graphora.store` in-process.

### Incremental Delivery

1. US1 → the store exists and is trustworthy.
2. US2 → the frontend can read real graphs and files over HTTP.
3. Polish → performance targets and the shared-file follow-up.

## Notes

- `[P]` = different files, no dependency on unfinished tasks.
- `ingest/fetch.py` belongs to Anna: T016 is the only change there; request her review.
- Never edit an existing test, `expected.json` or `schema/graph.schema.json` in this feature.
