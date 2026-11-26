---

description: "Task list for 014-hotspots"
---

# Tasks: Hotspots

**Input**: Design documents from `specs/014-hotspots/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R11), data-model.md, contracts/graph-schema-v8.md,
contracts/interfaces.md, contracts/verifier.md, quickstart.md

**Tests**: Required (constitution VIII). Within each phase, write the tests first and confirm they fail. Expected
counts are written by hand in the tests, never taken from the reader's output.

**Organization**: Phase 2 (history model, schema v8, test git repositories) blocks every story. Then:

- US1 (P1): local git history is read and hotspots are ranked (MVP);
- US2 (P1): missing, skipped, dirty, partial and GitHub histories are reported honestly;
- US3 (P2): MCP, HTTP and the verifier answer hotspots from the stored graph.

Paths are relative to the repository root. Code lives in `backend/src/graphora/`, tests in `backend/tests/`.
Run commands from `backend/`. Keep comments minimal, in the style of the existing modules (one short module
docstring with a spec reference, one-line docstrings only where not obvious).

**Commits**: one commit after every task (a test task is committed on its own, before its implementation).
Messages are short, lowercase and English and name the task's change; the **Commit** lines below are the theme
of the group. Push at the end of each phase.

## Phase 1: Setup

- [X] T001 Create the package `backend/src/graphora/history/__init__.py` with a one-line module docstring
  referencing `specs/014-hotspots` and `HISTORY_READER_VERSION = "1.0.0"`.
- [X] T002 Create `backend/tests/history_repos.py`, a test helper that builds git repositories with dulwich only
  (no git binary).
  - `make_repo(path, commits)` takes a list of commit specs: `files` (path → bytes or `None` for delete),
    `author` (`"Name <mail>"`), `time` (UTC seconds), `parents` (indexes of earlier commits; default: the
    previous one; `[]` for a root; two or more for a merge).
  - It writes objects with `Repo.init`, `Blob`, `Tree` and `Commit`, sets `HEAD`, checks out the last tree into
    the working folder so `analyze` sees the files, and returns the commit SHAs.
  - It also offers `make_shallow(path, shas)`, which writes `.git/shallow`.

**Commit**: `history package and test repo helper`

---

## Phase 2: Foundational (history model, schema v8)

**Purpose**: the `history` section that every document carries (data-model.md, contracts/graph-schema-v8.md).

- [X] T003 [P] Write `backend/tests/unit/test_history_model.py`.
  - **Rules** (data-model.md § History): every rule raises `ValueError` when broken:
    - `not_available` needs a `reason`, and `commit`, `window_start`, `newest`, `oldest` None, all counts 0,
      `files` empty, `local_changes` false;
    - `available`/`partial` have `reason` None and `commit` and `window_start` set;
    - `newest`/`oldest` are set exactly when `commits_read > 0`;
    - `partial` needs `commits_read > 0`;
    - `files` are unique and sorted by path, each with `commits ≥ 1` and `1 ≤ authors ≤ commits`.
  - **`History.final`**: true for `available` and for `not_available` with `no_git`, `zip`, `unreadable`; false
    otherwise.
  - **Default**: `GraphDocument` without `history` gets `NOT_COLLECTED`.
- [X] T004 Add to `backend/src/graphora/graph/model.py`:
  - `HistoryStatus = Literal["available", "partial", "not_available"]`;
  - `HistoryReason = Literal["no_git", "zip", "unreadable", "skipped", "fetch_failed", "too_large",
    "time_limit", "not_collected"]`;
  - frozen `FileHistory(path, commits, authors)`;
  - frozen `History(status, reason, commit, window_start, newest, oldest, commits_read, merges_skipped,
    shallow_skipped, local_changes, files)` with `__post_init__` checks and the `final` property;
  - `NOT_COLLECTED`;
  - `GraphDocument.history: History = NOT_COLLECTED`.
  
  Extend the module docstring with "v8 adds history (specs/014-hotspots)". Run `uv run pytest
  tests/unit/test_history_model.py`.

**Commit**: `history model`

- [X] T005 [P] Extend `backend/tests/unit/test_serialize.py` and `backend/tests/unit/test_load.py`:
  - `schema_version` is 8;
  - `history` is written with all keys of contracts/graph-schema-v8.md, `files` sorted by path;
  - a round trip `loads(dumps(doc))` keeps `history`;
  - `loads` rejects (`InvalidGraph`): a missing `history`, an unknown status or reason, unsorted or duplicate
    files, a path that is not a file node, `authors > commits`, and a `commit` that differs from the snapshot
    id's SHA part for `available`/`partial`;
  - `extractors` contains `"history-reader": "1.0.0"`.
- [X] T006 Write the section in `backend/src/graphora/graph/serialize.py` (`SCHEMA_VERSION = 8`, `_history_dict`
  with sorted keys, called from `to_dict`). Read and check it in `backend/src/graphora/graph/load.py`
  (`_history`, with the checks of T005). Add `"history-reader": history.HISTORY_READER_VERSION` to
  `current_extractors()` in `backend/src/graphora/graph/build.py`.
- [X] T007 Update `schema/graph.schema.json` to v8 as contracts/graph-schema-v8.md says:
  - description "Schema version 8";
  - `schema_version` const 8;
  - `history` required;
  - a `history` `$def` with the key rules and the `if`/`then` for `not_available`.
  
  Update `backend/tests/contract/test_schema.py` so a v8 example with each status validates and a
  `not_available` history with files does not.
- [X] T008 Update the version-pinned tests to v8: `backend/tests/unit/test_overview.py`,
  `backend/tests/integration/test_store.py`, `backend/tests/integration/test_query_cli.py` and
  `backend/tests/unit/extractor_versions.json` (add `history-reader`). Run `uv run pytest -m "not db and not
  slow"` and fix only version and expected-key fallout.

**Commit**: `graph schema v8 with history section`

- [X] T009 Add `"history"` to `project()` in `backend/tests/conftest.py` (copied as is) and to the sections of
  `test_matches_expected` in `backend/tests/golden/test_fixtures.py`. No fixture has the section yet, so the new
  case is skipped and the suite stays green; the fixtures get it in T017.

**Commit**: `golden tests: history section`

**Checkpoint**: push. `make check` passes.

---

## Phase 3: User Story 1 — See the riskiest files of a snapshot (Priority: P1) 🎯 MVP

**Goal**: a local git folder gets a counted history and a ranked hotspot list (spec US1, FR-001–FR-007,
FR-009; research R2–R4, R8).

**Independent Test**: build a repository with `history_repos.make_repo`, run `graphora analyze` and `graphora
query … hotspots`, and compare commits, authors, dependents, score and order with hand-written values.

### Tests

- [X] T010 [P] [US1] Write `backend/tests/unit/test_history_reader.py` against `reader.read_history(store,
  commit_sha, paths, shallow, deadline)`, on repositories from `history_repos`. Hand-written expectations:
  - a file changed in 5 commits by one author → `commits 5, authors 1`;
  - two authors with the same e-mail in different case and different names count as 1; different e-mails count
    as 2;
  - a merge commit is not counted and increases `merges_skipped`, while both branches' commits are counted;
  - a delete is not counted; a rename counts for the new path only;
  - a root commit counts every file it adds;
  - a commit older than snapshot time − 365 × 86,400 s is not counted, and its ancestors are not walked;
  - a commit exactly at the window start is counted;
  - paths not in `paths` (for example `README.md`, `.venv/x.py`) are absent from `files`;
  - `newest`/`oldest`/`window_start` are `YYYY-MM-DDTHH:MM:SSZ` from commit times;
  - two reads give equal results.
- [ ] T011 [P] [US1] Write `backend/tests/unit/test_hotspots_query.py` on synthetic `GraphDocument`s
  (`tests/unit/synthetic.py` style) with a hand-made `History`:
  - `score = commits × transitive_dependents`, e.g. 5 × 3 = 15 (spec US1 scenario 1);
  - order by score, then commits, then transitive dependents, then path (scenario 2);
  - a file with history but no dependents, and a file with dependents but no history, are left out
    (scenario 3);
  - `direct_dependents` is reported;
  - `include_type_only=False` uses runtime links only, like `key_files`;
  - `limit` gives `total` and `truncated`, and a negative limit raises `ValueError`;
  - the answer carries `history` without `files`;
  - `render_text` matches the contract lines.
- [ ] T012 [P] [US1] Write `backend/tests/integration/test_history_cli.py` (local folder part):
  - **analyze**: on a built repository, `run_analyze(repo)` writes `history.status available` with the
    hand-written counts per file, and stderr has the `history:` info line;
  - **repeat**: a second run gives identical bytes (SC-002);
  - **query**: `graphora query <out> hotspots` text and `--format json` list the expected items;
  - **usage errors**: `hotspots` with a target, `--symbol`, `--max-depth`, `--follow-barrels` or `--level
    project` exits 2;
  - **privacy** (FR-015): the graph bytes and the query output contain none of the test authors' names or
    e-mail addresses.

### Implementation

- [X] T013 [US1] Implement `backend/src/graphora/history/reader.py`: `read_history(store, commit_sha,
  paths: frozenset[str], shallow: frozenset[bytes], deadline) -> History`, per research R3, R4.
  - **Walk**: a heap of `(-commit_time, sha)`; the window start is the snapshot commit time − 365 × 86,400.
  - **Counting**: merges are skipped and counted in `merges_skipped`; shallow commits are skipped and counted in
    `shallow_skipped`; for one parent use `tree_changes(store, parent.tree, commit.tree)`, for a root use
    `tree_changes(store, None, commit.tree)`. Keep `add`/`modify` new paths that are in `paths`.
  - **Authors**: lower-case e-mail between `<` and `>`, or the whole author string in lower case.
  - **Dates**: formatted with `datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")`.
  - **Output**: only counts.
  
  Leave the time limit for T024. Run `uv run pytest tests/unit/test_history_reader.py`.

**Commit**: `history reader for local commits`

- [ ] T014 [US1] Implement `backend/src/graphora/history/local.py`: `local_source(root, snapshot)`. It returns
  `(Repo, sha, shallow, dirty)` or a `not_available` reason:
  - `no_git` for a `content:` snapshot or when `ingest.snapshot._usable_git_dir(root)` is false;
  - `unreadable` for any dulwich error.
  
  The SHA is the snapshot id's part before `+dirty:`. In `backend/src/graphora/history/__init__.py` add
  `collect_history(root, snapshot, doc, *, kind, deadline, enabled=True, fetch=None) -> History`:
  - the paths are the document's file node paths;
  - for a local source it calls `reader.read_history` and sets `local_changes` for a dirty snapshot;
  - it always closes the repository.
- [ ] T015 [US1] Add `hotspots(ix, *, include_type_only=True, limit=10)` to
  `backend/src/graphora/graph/queries.py` per research R8:
  1. call `key_files(..., limit=None)`;
  2. join by path with `ix.doc.history.files`;
  3. keep `score > 0`;
  4. sort `(-score, -commits, -transitive_dependents, node)`;
  5. return `_answer(..., history=...)`.
  
  In `backend/src/graphora/graph/results.py`:
  - add `"hotspots"` to `Question`;
  - add `commits`, `authors`, `score` to `Item` (written only when not None);
  - add `Answer.history` (the summary without `files`, written as `history`);
  - add `_hotspot_lines`, and a `history:` footer line per contracts/interfaces.md (partial, not available,
    skipped, local changes, shallow wording).
  
  Run `uv run pytest tests/unit/test_hotspots_query.py`.

**Commit**: `hotspots query and answer`

- [ ] T016 [US1] Add a `FetchedSnapshot.kind` field (`"local" | "github" | "zip"`) in
  `backend/src/graphora/ingest/fetch.py` (set in each branch of `fetch_snapshot`). Add a shared helper
  `with_history(doc, fetched, deadline, enabled)` in `backend/src/graphora/history/__init__.py` that returns
  `dataclasses.replace(doc, history=collect_history(...))`.
- [ ] T017 [US1] Call `with_history` after `build`/`analyze` in both flows:
  - `_analyze` in `backend/src/graphora/cli/__init__.py`;
  - `run_pipeline` in `backend/src/graphora/pipeline/run.py`, inside the `fetch_snapshot` block, before
    storing.
  
  Add to the CLI:
  - the `history:` info line after the summary, same text as the query footer;
  - `hotspots` to `_QUESTIONS` with no target;
  - `--limit` default 10, like `key-files`;
  - the same option errors as `key-files`.
  
  Write a `history` section by hand into every `fixtures/repos/*/expected.json`: `{"status": "not_available",
  "reason": "no_git", …}` with all keys of contracts/graph-schema-v8.md (the fixtures are not git roots). Run
  `uv run pytest tests/integration/test_history_cli.py tests/golden/test_fixtures.py`.

**Commit**: `history in analyze, query hotspots`

**Checkpoint**: push. US1 works for local folders (quickstart § 2).

---

## Phase 4: User Story 2 — Hotspots are honest about missing history (Priority: P1)

**Goal**: ZIP, plain folders, `--no-history`, unreadable `.git`, dirty trees, shallow clones, the time limit
and GitHub sources each give the right status and reason, and the store keeps the best history (spec US2,
FR-008, FR-008a, FR-010, FR-011, FR-014, FR-016, FR-017, FR-018; research R5–R7).

**Independent Test**: analyze a ZIP, a plain folder, a dirty repository, a shallow repository, a repository
with an expired deadline, and a repository served by a local git server; check status, reason and notes.

### Tests

- [ ] T018 [P] [US2] Extend `backend/tests/integration/test_history_cli.py`:
  - a ZIP of a built repository → `not_available` / `zip` (a `.git` folder in the archive is dropped at
    extraction, `ingest/archive.py`, so the reason is `zip` either way);
  - a plain folder → `no_git`;
  - `--no-history` → `skipped`, with the info line `not available (skipped by request)`;
  - a `.git` with `objects/info/alternates` → `no_git`, same rule as the snapshot id;
  - an older commit object deleted from `.git/objects`, while HEAD and its tree stay readable (so the snapshot
    id is still the SHA) → `unreadable`;
  - an uncommitted change → `local_changes true`, HEAD's counts, and the note in the info line;
  - `make_shallow` on a middle commit → `shallow_skipped 1` and the shallow note;
  - in none of these cases `analyze` exits non-zero.
- [ ] T019 [P] [US2] Add partial-history cases to `backend/tests/unit/test_history_reader.py` with a fake
  deadline whose `remaining()` drops to 0 after N commits:
  - status `partial`, `commits_read == N`, and the newest N commits in walk order;
  - `oldest` is the date of the N-th;
  - with N = 0 → `not_available` / `time_limit`;
  - the reader never raises `LimitExceeded`.
- [ ] T020 [P] [US2] Write `backend/tests/integration/test_history_github.py`. Serve a built repository with
  `dulwich.web.make_wsgi_chain` from a `wsgiref` server on `127.0.0.1` in a thread, and point
  `history.github` at it through a test hook (module-level base URL function, like `ingest.github._open`).
  Cases:
  - **fetch**: a fetch for the head SHA gives the same `History` as reading the repository locally, and no
    blob objects are stored when the server honours `blob:none`;
  - **too_large**: a pack over `max_archive_bytes` → `not_available` / `too_large`;
  - **time_limit**: an expired deadline → `time_limit`;
  - **fetch_failed**: a 500, a 301 redirect, or a SHA the server does not have;
  - **cleanup**: the temp bare repository lies outside the snapshot root and is removed after the
    `fetch_snapshot` block.
  - With the tarball faked as in 002 (`tests/fake_github.py`), `run_analyze("https://github.com/o/r")` writes
    `history.available`.
- [ ] T021 [P] [US2] Write `backend/tests/integration/test_history_store.py` (marked `db`):
  - a stored analysis with `skipped` is replaced by a later run with `available` (action `replaced`);
  - one with `available` is reused by a `--no-history` run;
  - `partial` is not reused by the pipeline's reuse check when history is wanted;
  - `zip` and `no_git` are final.
  
  Also cover jobs in `backend/tests/integration/test_api_jobs.py`:
  - `{"history": false}` gives `skipped`;
  - a non-boolean `history` gives 400;
  - the job body echoes `history`;
  - two jobs that differ only by `history` are not deduplicated.

### Implementation

- [ ] T022 [US2] Implement `backend/src/graphora/history/github.py`: `fetch_history(source, sha, workdir,
  limits, deadline) -> (store, shallow) | reason`, per research R5.
  - **Client**: `Urllib3HttpGitClient` on `https://github.com/<owner>/<repo>.git` (base URL behind a test
    hook), with the 002 User-Agent, `Retry(redirect=0)` and per-request timeout `deadline.remaining()`.
  - **Step 1**: `fetch_pack` with `depth=1`, `filter_spec=b"blob:none"`, `determine_wants` returning `[sha]`.
    This gives the commit time.
  - **Step 2**: `shallow_since` = window start − 30 days, as `"<unix seconds>"`, with `blob:none`.
  - **Storage**: `pack_data` writes into `object_store.add_pack()` of `Repo.init_bare(workdir / "history.git")`,
    counts bytes and stops over `max_archive_bytes` (`too_large`). It checks the deadline (`time_limit`).
    Record `new_shallow` in the shallow file.
  - **Errors**: any `HTTPError`, `GitProtocolError` or OS error → `fetch_failed`.
- [ ] T023 [US2] Wire GitHub and ZIP into `collect_history` in `backend/src/graphora/history/__init__.py`:
  - `kind == "zip"` → `zip`;
  - `kind == "github"` → `fetch_history` into a sibling folder of the snapshot root inside the fetch temp
    folder, then `reader.read_history` on it;
  - `enabled=False` → `skipped`, before any read or network.
  
  Let `fetch_snapshot` in `backend/src/graphora/ingest/fetch.py` expose the temp folder and the GitHub source
  on `FetchedSnapshot`, so `with_history` can fetch. Run `uv run pytest
  tests/integration/test_history_github.py`.

**Commit**: `github history fetch`

- [ ] T024 [US2] Add the time limit to `backend/src/graphora/history/reader.py`:
  - check `deadline.remaining() <= 0` before each commit;
  - when time runs out, return `partial` with what was read, or `not_available` / `time_limit` when nothing was
    read;
  - never raise.
  
  Run `uv run pytest tests/unit/test_history_reader.py`.
- [ ] T025 [US2] Add `--no-history` to `analyze` in `backend/src/graphora/cli/__init__.py`, passed to
  `with_history(enabled=...)` and to `run_pipeline(..., history=...)` in
  `backend/src/graphora/pipeline/run.py`. In `run_pipeline`, reuse a stored analysis before fetching only if
  `not history` or its history is final. Read it from the stored graph JSON with a helper `history_final(graph:
  bytes) -> bool` in `backend/src/graphora/history/__init__.py`.
- [ ] T026 [US2] In `backend/src/graphora/store/store.py` `put`, keep reusing an existing analysis, except when
  its stored history is retryable and the new document's history is final. Then replace it (FR-018, research R6). Read
  the stored graph's `history` with `history_final`.
- [ ] T027 [US2] Add the jobs flag in `backend/src/graphora/api/jobs.py` and
  `backend/src/graphora/pipeline/jobs.py`:
  - body key `history` (boolean, default true; anything else → 400 `history must be true or false`);
  - ZIP query parameter `history=true|false`;
  - `_Job.history`, echoed as `"history"` in the status body;
  - included in the GitHub dedup key and passed to `run_pipeline`.
  
  Run `uv run pytest -m db tests/integration/test_history_store.py tests/integration/test_api_jobs.py`.

**Commit**: `no-history option, store keeps the best history`

**Checkpoint**: push. US1 and US2 work (quickstart § 3, § 4).

---

## Phase 5: User Story 3 — Agents and tools ask for hotspots and the answer verifies (Priority: P2)

**Goal**: CLI, MCP and HTTP return the same hotspots; hotspot claims verify (spec US3, FR-012, FR-013;
research R9, R10; contracts/interfaces.md, contracts/verifier.md).

**Independent Test**: for a stored built repository, compare CLI JSON, MCP tool output and the HTTP body; check
true and wrong hotspot claims with the verifier.

### Tests

- [ ] T028 [P] [US3] Write `backend/tests/unit/test_verify_hotspots.py` on a synthetic document with a hand-made
  history:
  - `rank` 1 of the top file is `verified`;
  - a wrong rank → `rank_mismatch`, hint `rank N`;
  - `metric commits` with the right value is `verified`; a wrong value → `count_mismatch`, hint `actual N`;
    the same for `authors`, `score`, `transitive_dependents`, `direct_dependents`;
  - `count` of hotspots;
  - a member that is not a hotspot → `not_in_result`;
  - history `not_available` → `history_unavailable`, hint is the reason;
  - history `partial` → `heuristic`;
  - validation errors: `metric` without `value`, `metric` on `key_files`, a target given, an unknown option,
    an unknown metric;
  - verdict JSON is byte-identical on two calls.
- [ ] T029 [P] [US3] Extend `backend/tests/integration/test_mcp_store.py` (or a new
  `backend/tests/integration/test_mcp_hotspots.py`, `db`):
  - the `hotspots` tool is listed as read-only with the fixed description;
  - its output equals `render_text` of `queries.hotspots`;
  - `limit` above `MAX_LIMIT` is refused like other tools;
  - `graph_overview` shows the history line.
  
  Write `backend/tests/integration/test_hotspots_api.py` (`db`):
  - `GET /api/v1/hotspots` returns the bytes of `results.dumps(queries.hotspots(...))`;
  - unknown repository or snapshot → 404;
  - bad `limit`, bad `include_type_only`, an unknown or repeated parameter → 400;
  - a ZIP snapshot gives 200 with empty items and reason `zip`.

### Implementation

- [ ] T030 [US3] In `backend/src/graphora/verify/claims.py`:
  - add `"hotspots"` to `ALLOWED_OPTIONS` with `include_type_only`;
  - add the `Claim` fields `metric` and `value` (quoted from data-model.md: "`metric` (`commits` \| `authors` \|
    `score` \| `transitive_dependents` \| `direct_dependents`) and `value` (int ≥ 0). Both are optional, given
    together, and allowed only for `question: "hotspots"` with a `member`");
  - allow `rank` for `hotspots`;
  - add `history_unavailable` to `Reason`.
  
  In `backend/src/graphora/verify/graph_checks.py` add `hotspots` to `_ASK` and a `_hotspot` check in the order
  of contracts/verifier.md. The checks list ends with `history`. Run `uv run pytest
  tests/unit/test_verify_hotspots.py tests/unit/test_verify_claims.py`.

**Commit**: `verify hotspot claims`

- [ ] T031 [US3] In `backend/src/graphora/mcp/server.py`:
  - add the `hotspots(include_type_only=True, limit=10)` tool with the fixed description of
    contracts/interfaces.md, calling `queries.hotspots` through `ask`;
  - add `history` to `Overview` in `backend/src/graphora/graph/results.py` (JSON `{status, reason}` and a text
    line) and set it in `queries.overview`.
- [ ] T032 [US3] Add `GET /api/v1/hotspots` to `backend/src/graphora/api/routes.py`:
  - `_params(request, ("repository", "snapshot"), ("limit", "include_type_only"))`;
  - `include_type_only` must be `true` or `false`;
  - load the stored graph with `graph.load.loads`, index it, call `queries.hotspots`;
  - respond with `results.dumps` as `application/json`.
  
  Run `uv run pytest -m db tests/integration/test_hotspots_api.py tests/integration/test_mcp_store.py`.

**Commit**: `hotspots over mcp and http`

**Checkpoint**: push. All stories work (quickstart § 5, § 6).

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T033 [P] Write `backend/tests/integration/test_history_performance.py` (marked `slow`): build a repository
  of 5,000 files in nested folders and 10,000 commits touching 1–5 files each, all within the window. Reading
  its history takes ≤ 30 s (SC-003).
- [ ] T034 [P] Add the new commands to `CLAUDE.md`: `uv run graphora analyze <source> --no-history` and `uv run
  graphora query graph.json hotspots`. Add a short history note under Commands: history is on by default; ZIP
  sources have none.
- [ ] T035 Run `make check` (with `make db` and `GRAPHORA_TEST_DATABASE_URL`) and `make lint`. Walk through
  quickstart.md §§ 2–6 and fix what differs. SC-003a (GitHub fetch ≤ 60 s) has no automated test: measure it
  by hand in quickstart § 4 and write the time in the PR description. Mark tasks done in this file.

**Commit**: `hotspots: performance test, docs`

**Checkpoint**: push; mark PR #35 ready for review.

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2**: T003–T009 need T001 and T002.
- **Phase 2 blocks all stories**: `History` and schema v8 must exist.
- **US1 (Phase 3)** needs Phase 2. **US2 (Phase 4)** needs US1's reader, `collect_history` and `with_history`
  (T013, T014, T016, T017). **US3 (Phase 5)** needs `queries.hotspots` (T015); its store and HTTP tests also
  need T017.
- **Within a phase**: tests [P] first; then implementation in task order. T024 must come after T019. T026
  needs T025's `history_final`.
- **Polish** after all stories.

## Parallel Opportunities

- Phase 2: T003 and T005 (different test files).
- US1: T010, T011 and T012 together; T013 and T015 touch different files and can go in parallel after the
  tests.
- US2: T018, T019, T020 and T021 together; T022 (GitHub fetch) and T024 (time limit) touch different files.
- US3: T028 and T029 together; T030 (verifier) and T031/T032 (MCP, HTTP) are independent.
- Polish: T033 and T034.

## Implementation Strategy

1. **MVP**: Phases 1–3. Local git folders get hotspots through `analyze` and `query`, and the golden fixtures
   pass. Stop and check with quickstart § 2.
2. **Honest history**: Phase 4 adds every missing-history case, GitHub and the store rule. This is the second P1
   story and must land before the PR is ready.
3. **Surfaces**: Phase 5 adds MCP, HTTP and the verifier for agents (012/013) and the frontend.
4. **Polish**: Phase 6, then review by Ulyana (schema v8, store rule, API changes).
