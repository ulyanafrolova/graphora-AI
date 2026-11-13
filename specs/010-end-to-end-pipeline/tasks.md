---

description: "Task list for 010-end-to-end-pipeline"
---

# Tasks: End-to-End Pipeline (Import and Analyze over HTTP)

**Input**: Design documents from `specs/010-end-to-end-pipeline/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R12), data-model.md, contracts/http-api.md,
contracts/cli.md, contracts/pipeline-api.md, quickstart.md

**Tests**: Required. Constitution VIII (golden equivalence, repeated runs) and SC-001 … SC-007 are checked by
tests. Within each story write the tests first and confirm they fail before implementing.

**Organization**: Tasks are grouped by user story:

- US1 (P1): import a GitHub repository over HTTP and get its graph;
- US2 (P1): a commit that is already stored is not analyzed again;
- US3 (P2): upload a ZIP archive over HTTP;
- US4 (P2): failures are reported clearly and leave no trace.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: The user story the task belongs to (US1 … US4)

Paths are relative to the repository root. Code lives in `backend/src/graphora/`, tests in
`backend/tests/`. Run commands from `backend/`. Do not edit any existing test or `expected.json` (SC-007),
except where a task says so. Tests that need PostgreSQL carry `@pytest.mark.db`. Tests never sleep for a
fixed time: they poll with `wait_for_job` (T001) or wait on `threading.Event`s.

---

## Phase 1: Setup

**Purpose**: Shared test helpers. No new dependency (plan: Technical Context). The `job_app` fixture
needs `JobRunner`, so it is written with the US1 tests (T011).

- [ ] T001 [P] Add `backend/tests/jobs_helpers.py`:
  - `wait_for_job(client, job_id, timeout=30.0) -> dict`: polls `GET /api/v1/jobs/{job_id}` every 0.02 s
    until `stage` is `done` or `failed`, returns the parsed body; fails the test with the last body on
    timeout;
  - `stages_seen(client, job_id) -> list[str]`: like `wait_for_job` but records every distinct `stage` in the
    order seen;
  - `fixture_tarball(name, sha) -> bytes`: `archives.tar_of_dir(FIXTURES / name / "repo",
    prefix=f"o-{name}-{sha[:7]}", pax_comment=sha)`, the tarball shape GitHub serves;
  - `fixture_zip(name) -> bytes`: `archives.zip_of_dir(FIXTURES / name / "repo")`.
- [ ] T002 [P] Add to `backend/tests/conftest.py` a fixture `fake_gh(monkeypatch)` that installs
  `fake_github.FakeGitHub()` as `graphora.ingest.github._open` and returns it (same as `fake` in
  `tests/integration/test_store_cli.py`, which stays unchanged).

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: One analyze-and-store function for the CLI and the service (research R2, R8, R11).
After this phase `graphora analyze --store` runs through `run_pipeline` with byte-identical output.

- [ ] T003 [P] Write `backend/tests/unit/test_fetch_workdir.py`: `fetch_snapshot(ZipSource(zip), limits,
  deadline, workdir=d)` yields a root inside `d`, and `d` is empty again after the `with` block, on success
  and when the block raises; same for a GitHub source with `fake_gh`; `workdir=None` still uses the system
  temp folder.
- [ ] T004 Add the optional parameter `workdir: Path | None = None` to `fetch_snapshot` in
  `backend/src/graphora/ingest/fetch.py` and pass it as `dir=workdir` to both
  `tempfile.TemporaryDirectory(prefix="graphora-")` calls. Update the docstring. No other change (Anna's
  module, research R8).
- [ ] T005 [P] Create `backend/src/graphora/pipeline/messages.py`: move `_LIMIT_MESSAGES` from
  `backend/src/graphora/cli/__init__.py` and expose `limit_message(exc: LimitExceeded, style: Literal["cli",
  "api"]) -> str`. `cli` keeps the exact current text (`--max-files`, `--max-bytes`, `--max-seconds`,
  `--max-archive-bytes`, `--max-extract-bytes`, `--max-entries`); `api` uses `max_files`, `max_bytes`,
  `max_seconds`, `max_archive_bytes`, `max_extract_bytes`, `max_entries`. Make the CLI call
  `limit_message(exc, "cli")`.
- [ ] T006 [P] Write `backend/tests/unit/test_pipeline_messages.py`: for each of the six limits, the `cli`
  text equals the pre-010 string and the `api` text uses the key name, e.g.
  `file limit exceeded: at least 5001 files > max_files 5000`.
- [ ] T007 Write `backend/tests/integration/test_pipeline_run.py` (`db`): `run_pipeline` on py-flat
  (`LocalSource`), a ZIP and a GitHub source via `fake_gh` returns the same `StoredAnalysis.graph` bytes as
  `graphora analyze --store` for the same input; `on_stage` receives `resolving, fetching, analyzing,
  storing` for GitHub, `fetching, analyzing, storing` for ZIP and local, and only `resolving` on a GitHub
  reuse; `PipelineResult.action` is `stored`, then `reused` on a second run; `fetched` is `None` on a GitHub
  reuse.
- [ ] T008 Create `backend/src/graphora/pipeline/run.py` and `backend/src/graphora/pipeline/__init__.py`
  per contracts/pipeline-api.md: `PipelineLimits` (frozen dataclass of the six limits; `max_seconds: float`),
  `PipelineResult(analysis, action, fetched)`, `Stage = Literal["resolving", "fetching", "analyzing",
  "storing"]`, and `run_pipeline(source, limits, store, deadline, on_stage=…, workdir=None)`. Move the body of
  `cli._analyze_and_store` into it: GitHub → `on_stage("resolving")`, `github.resolve_sha`,
  `store.find_reusable` (return `action="reused"`, `fetched=None` when found) → `on_stage("fetching")`,
  `fetch_snapshot(..., sha=sha, workdir=workdir)` → `on_stage("analyzing")`, `analyze(...)`,
  `with_skipped` → `on_stage("storing")`, `store.put`. The `fetched` text is the CLI info line
  (`fetched <repo> at <sha>` / `extracted <name>`), or `None` for a local folder. Raise exceptions
  unchanged.
- [ ] T009 Make `cli._analyze_and_store` in `backend/src/graphora/cli/__init__.py` open the store, call
  `run_pipeline` with a no-op `on_stage`, and build its info lines and `_Report` from `PipelineResult`
  exactly as before. Run `uv run pytest tests/integration/test_store_cli.py tests/integration/test_ingest_cli.py`:
  all pass unchanged (FR-022).

**Checkpoint**: shared pipeline in place; CLI unchanged.

---

## Phase 3: User Story 1 — Import a GitHub repository over HTTP (P1) 🎯 MVP

**Goal**: `POST /api/v1/jobs` with a GitHub link starts a background job; `GET /api/v1/jobs/{id}` shows its
stage; `done` names the stored repository and snapshot, readable through the 005 API and the MCP server.

**Independent Test**: empty store + `fake_gh` serving `fixture_tarball("ts-app", SHA)`: submit, wait, compare
`GET /api/v1/graph` bytes with `analyze --store` output.

### Tests for User Story 1

- [ ] T010 [P] [US1] Write `backend/tests/unit/test_jobs.py` with an injected stub `pipeline` (no database;
  pass `database_url="postgresql://unused"` and a stub that never opens a store):
  - `submit_github` returns a status with `stage == "queued"` and a 32-hex-character `id`; ids of 100 jobs
    are distinct;
  - with `workers=1`, a stub that blocks on an `Event` keeps the second job `queued`; jobs start in
    submission order;
  - stages reported through `on_stage` appear in the status; a stage that moves backwards is ignored
    (FR-006); `done` sets `result`, `failed` sets `error`, never both;
  - `status(id).to_json()` is byte-identical across calls for the same state, has sorted keys, no
    whitespace, and no time-like values (FR-009, research R6);
  - `status("nope")` and `status(<unknown 32 hex>)` are `None`.
- [ ] T011 [P] [US1] Add to `backend/tests/conftest.py` a fixture `job_app(store, database_url, tmp_path)`
  that builds `JobRunner(database_url, PipelineLimits(<CLI defaults>), workers=1, queue_size=20,
  work_dir=tmp_path / "jobs")`, calls `start()`, yields `(TestClient(create_app(store, runner)), runner)`,
  and calls `runner.stop()` afterwards; keyword overrides for `workers`, `queue_size`, limits and
  `database_url` come through indirect parametrization (`request.param`). Then write
  `backend/tests/integration/test_api_jobs.py` (`db`) section US1, using `job_app` and `fake_gh`:
  - `POST /api/v1/jobs {"github": "https://github.com/o/ts-app"}` → `202`, body `stage` in
    `{"queued", "resolving", "fetching", "analyzing", "storing", "done"}` (acceptance 1);
  - `stages_seen` is a subsequence of `queued, resolving, fetching, analyzing, storing, done` (acceptance 2);
  - the `done` body has `result.repository == "github.com/o/ts-app"`, `result.snapshot == SHA`,
    `result.action == "stored"`, and `files`, `edges`, `unresolved`, `warnings` equal to the CLI summary for
    the same tarball (acceptance 3);
  - `GET /api/v1/graph?repository=…&snapshot=…` bytes equal `graphora analyze https://github.com/o/ts-app
    --store` stdout run against the same fake (acceptance 4);
  - `graphora.mcp` in store mode opened with `result.repository`/`result.snapshot` answers `graph_overview`
    (reuse `tests/mcp_client.py`) (acceptance 5);
  - the 005 endpoints answer exactly as before for a store filled by a job (FR-022).

### Implementation for User Story 1

- [ ] T012 [US1] Implement `backend/src/graphora/pipeline/jobs.py` (data-model.md, research R1, R3, R6, R7,
  R11): `Job`, `JobStatus` with `to_json() -> bytes` (005 `json_bytes` rules: `sort_keys=True`,
  `separators=(",", ":")`, `ensure_ascii=False`), `QueueFull`, `Interrupted`, `JobDeadline(Deadline)` whose
  `check()` also raises `Interrupted` when the runner's stop event is set, and `JobRunner` with `start`,
  `stop`, `submit_github`, `status` per contracts/pipeline-api.md. Rules to keep verbatim:
  - `id`: "32 lower-case hex characters from `secrets.token_hex(16)`";
  - queue: "FIFO of queued job ids, length ≤ `queue_size` (default 20); full → `too_many_jobs`";
  - each running job opens its own `Store.open(database_url)` and closes it in `finally` (R3);
  - the `JobDeadline` is created when the job leaves the queue (FR-016);
  - each job runs with `workdir=<work_dir>/<id>/`, removed in `finally`;
  - exception → `kind` mapping exactly as research R11 (`StoreUnavailable` message is `store unavailable`;
    anything unexpected is `internal` / `internal error`, logged with traceback);
  - all state changes under one `threading.Lock`; `status()` serializes a copy taken under it.
  `start()` creates `work_dir` (default `Path(tempfile.gettempdir()) / "graphora-jobs"`); the lock and
  cleanup of leftovers come in US4 (T027).
- [ ] T013 [US1] Create `backend/src/graphora/api/jobs.py` with `router(runner) -> APIRouter` (prefix
  `/api/v1`):
  - `POST /jobs`: parse the JSON body by hand (not via a Pydantic model, so messages stay ours); allowed
    keys `github` (required string), `ref` (string), `limits` (object); unknown key → `bad_request`
    `unknown key: <k>`; a `github` value that does not start with a URL scheme → `bad_request`
    `not a GitHub repository link: <value>` without calling `parse_source` (FR-003, R9); otherwise
    `parse_source(github, ref)` and map `BadInput` to `bad_request`, rewriting `--ref` to `ref` in the
    message; reject a non-GitHub result. Limits: keys among the six names, integers ≥ 1 (`max_seconds` a
    number > 0), each ≤ the server value, else `bad_request` naming the key. Return `202` +
    `status.to_json()`.
  - `GET /jobs/{job_id}`: no query parameters; unknown or malformed id → `not_found` `job not found: <id>`.
- [ ] T014 [US1] Update `backend/src/graphora/api/__init__.py`: `create_app(store, runner=None)`; include
  `api.jobs.router(runner)` only when `runner` is given. Update `backend/src/graphora/api/errors.py`: the
  `405` message becomes `method not allowed`; add handlers so `QueueFull` → `429 too_many_jobs`
  `too many jobs waiting: <queue_size>`.
- [ ] T015 [US1] Update `graphora serve` in `backend/src/graphora/cli/__init__.py` per contracts/cli.md:
  options `--workers` (1), `--queue` (20), `--work-dir`, and the six `--max-*` limits with the `analyze`
  defaults; values below 1 → exit 2. Build `JobRunner(url, limits, …)`, `start()` before
  `uvicorn.run(create_app(store, runner), …)`, `stop()` in `finally`. `--host` stays `127.0.0.1` by default.
- [ ] T016 [US1] Run `uv run pytest tests/unit/test_jobs.py tests/integration/test_api_jobs.py
  tests/integration/test_api.py`: all pass.

**Checkpoint**: MVP — a GitHub link becomes a stored, queryable graph through HTTP.

---

## Phase 4: User Story 2 — A stored commit is not analyzed again (P1)

**Goal**: reuse by commit with no download; identical unfinished submissions share one job.

**Independent Test**: count tarball requests in `fake_gh` across repeated and concurrent submissions.

### Tests for User Story 2

- [ ] T017 [P] [US2] Add to `backend/tests/unit/test_jobs.py`: two `submit_github` calls with the same
  `(owner, repo, ref, limits)` while the first job is unfinished return the same id; a different `ref` or
  different limits create a new job; after the first job ends, the same submission creates a new job
  (research R10).
- [ ] T018 [P] [US2] Add section US2 to `backend/tests/integration/test_api_jobs.py` (`db`):
  - after a `done` job, the same link again ends `done` with `action == "reused"` and
    `fake_gh.urls("codeload.github.com")` has exactly one request in total (acceptance 1, SC-003: the second
    job finishes in under 2 s);
  - ten identical `POST`s while a stub-blocked first job runs return one id, and exactly one tarball
    request happens (acceptance 2, SC-004) — block by serving the tarball as an iterator that waits on an
    `Event`;
  - a stored analysis with a different `extractors` value (update the row directly, as the 005 store tests
    do) is analyzed again and the job reports `replaced` (acceptance 3);
  - two refs resolving to the same SHA end with one stored analysis (edge case).

### Implementation for User Story 2

- [ ] T019 [US2] Add the dedup index to `JobRunner` in `backend/src/graphora/pipeline/jobs.py`: key
  `("github", owner, repo, ref or "", limits)`; look it up and insert under the runner lock in
  `submit_github`; remove the entry when the job reaches `done` or `failed`. Reuse and replace already come
  from `run_pipeline` (T008); make sure a GitHub reuse moves `resolving → done` with `action "reused"`.

**Checkpoint**: US1 + US2 cover the whole GitHub flow.

---

## Phase 5: User Story 3 — Upload a ZIP archive over HTTP (P2)

**Goal**: `POST /api/v1/jobs/zip?name=…` with the archive as raw body; size limit enforced while
receiving; same job flow.

**Independent Test**: upload `fixture_zip("py-flat")`, compare with `graphora analyze <file.zip> --store`.

### Tests for User Story 3

- [ ] T020 [P] [US3] Write `backend/tests/unit/test_job_input.py` for the name and limit checks (functions
  from T023): rejected names `""`, `"."`, `".."`, `"../x.zip"`, `"a/b.zip"`, `"a\\b.zip"`, `"x\x00.zip"`, a
  256-byte name, a name whose repository part is longer than 300 characters; accepted `app.zip`,
  `my.repo.zip` (repository `my.repo`), `noext` (repository `noext`); limits above the server value, below 1,
  non-integer, unknown key → rejected with the key in the message.
- [ ] T021 [P] [US3] Add section US3 to `backend/tests/integration/test_api_jobs.py` (`db`):
  - `fixture_zip("py-flat")` uploaded as `app.zip` ends `done` with `repository == "app"` and the same
    `content:` snapshot and graph bytes as `graphora analyze app.zip --store` (acceptance 1);
  - `?max_archive_bytes=100` with a larger body → `413 limit` with
    `archive size limit exceeded: at least … bytes > max_archive_bytes 100`, no job created, nothing left in
    the work folder (acceptance 2); a `Content-Length` above the limit is rejected before the body is read;
  - every hostile archive used by `tests/integration/test_safety_ingest.py` for ZIP (traversal, absolute
    path, symlink escape, `bomb_zip`) ends `failed` with kind `archive` (or `limit` for the bomb) and the
    same reason as the CLI; no file appears outside `work_dir` (acceptance 3, SC-006);
  - the same archive uploaded twice → two `done` jobs, one stored analysis (acceptance 4);
  - an empty body or a body without a ZIP signature → `400` `not a ZIP archive: <name>`, no job.

### Implementation for User Story 3

- [ ] T022 [US3] Add `can_accept() -> bool`, `new_upload(name) -> Path` and `submit_zip(upload, limits)` to
  `JobRunner` in `backend/src/graphora/pipeline/jobs.py`: `new_upload` creates `<work_dir>/<new id>/upload/`
  and returns `<that folder>/<name>`, so `fetch_snapshot` names the repository after the uploaded name with
  no change to `ingest/`; `submit_zip` reuses that id and runs `run_pipeline(ZipSource(upload), …,
  workdir=<work_dir>/<id>/)`; an upload folder never passed to `submit_zip` is removed by the API handler
  (and by `start()` cleanup after a crash).
- [ ] T023 [US3] Add `POST /jobs/zip` to `backend/src/graphora/api/jobs.py` as an `async def` handler
  (research R4, R9): validate `name` (non-empty, at most 255 bytes, no `/`, `\` or NUL, not `.` or `..`,
  repository part 1–300 characters) and limits from query parameters; `429` if the queue is full; reject a
  `Content-Length` above `max_archive_bytes` with `413`; stream `request.stream()` into `new_upload()`,
  counting bytes, and stop with `413` as soon as the count passes the limit; then check the first 4 bytes
  against the ZIP signatures (`PK\x03\x04`, `PK\x05\x06`) → `400 not a ZIP archive: <name>`; then
  `submit_zip`. On any rejection remove the upload. Add the `ApiError` kind `limit` (413) to
  `backend/src/graphora/api/errors.py`.

**Checkpoint**: both MVP inputs work over HTTP.

---

## Phase 6: User Story 4 — Failures are clear and leave no trace (P2)

**Goal**: every failure kind reported with the CLI's reason; no partial analysis; no leftover files, also
after a crash; bounded queue; clean stop.

**Independent Test**: one input per failure kind; inspect status, store and `work_dir` after each.

### Tests for User Story 4

- [ ] T024 [P] [US4] Add section US4 to `backend/tests/integration/test_api_jobs.py` (`db`):
  - `{"github": "/etc"}`, `{"github": "https://gitlab.com/o/r"}`, an invalid ref, `/tree/x` plus `ref` →
    `400` with the CLI's reason (`ref` instead of `--ref`), no job (acceptance 1);
  - `fake_gh` answering `404` for the commit lookup → `failed`, kind `remote`, message names the repository
    or ref (acceptance 2);
  - `limits: {"max_files": 1}` on a 2-file tarball → `failed`, kind `limit`,
    `file limit exceeded: at least 2 files > max_files 1` (acceptance 3);
  - store unavailable: give the runner an unreachable `database_url` → `failed`, kind `store`, message
    `store unavailable`, and the message contains no part of the URL (acceptance 4);
  - `Store.put` patched to raise `InvalidAnalysis("x")` → kind `invalid`; a stub raising `RuntimeError` →
    kind `internal`, message `internal error`;
  - after every case: no analysis for that pair in the store, `work_dir` holds only `.lock` (acceptance 5,
    SC-005).
- [ ] T025 [P] [US4] Write `backend/tests/integration/test_jobs_cleanup.py`:
  - a second `JobRunner` on the same `work_dir` fails `start()` with `WorkDirInUse`; a different `work_dir`
    works;
  - leftovers (a folder and a file) in `work_dir` from a "killed" runner are removed by `start()`; `.lock`
    stays;
  - `stop()` while a job runs (stub pipeline looping on `deadline.check()`) ends it `failed/interrupted`
    and queued jobs `failed/interrupted`; no thread is left alive; the job folders are gone;
  - with `queue_size=2` and a blocked worker, the third waiting submission gets `QueueFull`, and over HTTP
    `429 too_many_jobs`.
- [ ] T026 [P] [US4] Add to `backend/tests/integration/test_store_cli.py` one test (allowed edit: new test
  only) that `graphora serve --workers 0` exits 2, and one that a second `serve` on a locked `--work-dir`
  exits 2 with `work folder in use by another graphora serve: use --work-dir` (mock `uvicorn.run`).

### Implementation for User Story 4

- [ ] T027 [US4] In `JobRunner.start()` (`backend/src/graphora/pipeline/jobs.py`): open
  `<work_dir>/.lock`, take `fcntl.flock(fd, LOCK_EX | LOCK_NB)`; on `BlockingIOError` raise `WorkDirInUse`;
  then remove every entry of `work_dir` except `.lock` (`shutil.rmtree` for folders, never following
  symlinks). Keep the fd open until `stop()` (research R8).
- [ ] T028 [US4] In `JobRunner.stop()`: stop accepting submissions (a submission after `stop()` raises
  `Stopping`, which the API answers with `503` kind `stopping`, message `the service is stopping`; add it to
  `backend/src/graphora/api/errors.py`), mark queued jobs `failed/interrupted`, set the stop event, join the
  worker threads, release the work-folder lock.
- [ ] T029 [US4] Map `WorkDirInUse` in `graphora serve` to exit 2 with the message from contracts/cli.md;
  map `OSError` creating `--work-dir` to exit 2 `cannot create work folder: <strerror>`.
- [ ] T030 [US4] Run the US4 tests and the full `uv run pytest -m "not slow"`: all pass.

**Checkpoint**: all four stories pass independently.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T031 [P] Write `backend/tests/golden/test_pipeline_equivalence.py` (`db`, SC-001): for every fixture
  in `fixtures/repos/`, (a) serve `fixture_tarball(name, sha)` through `fake_gh` and submit the link, (b)
  upload `fixture_zip(name)`; each stored graph equals `graphora analyze --store` bytes for the same input;
  run the whole loop 3 times with the store truncated in between and compare all bytes.
- [ ] T032 [P] Add a timing check to `backend/tests/integration/test_api_jobs.py`: `POST /api/v1/jobs`
  answers in under 1 s while a blocked job is running (SC-002).
- [ ] T033 [P] Update `CLAUDE.md` § Commands with `graphora serve` job options and a `curl` example for
  `POST /api/v1/jobs` (shared file: note it in the PR description).
- [ ] T034 [P] Update `docs/product/project-context.md` § 5 with the real endpoints (`/api/v1/repositories`,
  `/graph`, `/file`, `/jobs`, `/jobs/zip`, `/jobs/{id}`) and § 124 area if needed; note that `/ask` is
  feature 013.
- [ ] T035 Run `make check` from the repository root (ruff + full suite with PostgreSQL) twice; run the
  manual steps of `specs/010-end-to-end-pipeline/quickstart.md` 1–6 against real GitHub once and note the
  result in the PR description.
- [ ] T036 Update PR #25: mark ready, list the change to `ingest/fetch.py` for Anna's review, and the
  superseded 005 FR-018.

---

## Dependencies & Execution Order

- **Setup (T001–T002)**: in parallel.
- **Foundational (T003–T009)**: T004 after T003; T005/T006 in parallel with T003/T004; T008 after T004;
  T009 after T005 and T008. Blocks every story.
- **US1 (T010–T016)**: after Foundational. Tests T010, T011 first.
- **US2 (T017–T019)**: after US1 (same runner and endpoint).
- **US3 (T020–T023)**: after US1; independent of US2.
- **US4 (T024–T030)**: after US1; T024's ZIP-free cases do not need US3, its cleanup assertions use
  `work_dir` from T012.
- **Polish (T031–T036)**: after all stories; T031 needs US1 and US3.

### Parallel examples

- Foundational: T003 ‖ T005 ‖ T006.
- US1 tests: T010 ‖ T011.
- After US1: US2 (T017–T019) ‖ US3 (T020–T023) ‖ US4 tests (T024–T026).
- Polish: T031 ‖ T032 ‖ T033 ‖ T034.

## Implementation Strategy and Commits

Commits follow milestones, each one meaningful and pushed at once:

1. **Shared pipeline**: Setup T001–T002 + Foundational T003–T009 — the CLI runs through `run_pipeline`,
   output unchanged.
2. **Jobs over HTTP for GitHub**: US1 + US2 (T010–T019) — the MVP: link → stored graph, with reuse
   and dedup.
3. **ZIP upload and failures**: US3 + US4 (T020–T030).
4. **Final pass**: Polish (T031–T036) — golden equivalence, docs, `make check`, PR ready.

Stop after commit 2 to demo the MVP if needed: a GitHub link becomes a graph in the 005 API and MCP.
