# Research: End-to-End Pipeline (010)

All Technical Context unknowns are resolved below. Each entry: decision, rationale, alternatives.

## R1. Where jobs run: worker threads in the service process

**Decision**: A `JobRunner` owns a bounded FIFO queue and `workers` threads (default 1, `--workers`). Each
thread takes the next job and runs the shared pipeline function (R2) to the end. No new dependency.

**Rationale**: The service is local and single-user (spec Assumptions); one job at a time is the default.
Threads keep the whole suite in one process, so the existing test doubles keep working unchanged:
`fake_github` replaces `graphora.ingest.github._open` and the offline guard patches `socket` in-process.
Analysis already polls a `Deadline`, which gives a clean place to stop a job (R7). Store writes are already
safe across connections (`pg_advisory_xact_lock` per pair in `Store.put`).

**Alternatives considered**:
- *A child process per job* (`multiprocessing`, spawn): isolates a native crash (issue #8, tree-sitter
  segfaults) and allows a hard kill. Rejected for this slice: monkeypatched test doubles do not reach a
  spawned child, so every pipeline test would need a real local HTTP stand-in for GitHub; fork is unsafe on
  macOS with threads. The pinned tree-sitter versions fixed #8. Revisit if a native crash reappears.
- *A task queue (Celery, RQ, arq) with Redis*: new infrastructure for a local single-user tool; violates
  "do not add what the slice does not need".
- *FastAPI `BackgroundTasks`*: runs after the response on the request's worker, with no queue bound, no
  concurrency limit and no status; still needs everything `JobRunner` does.

## R2. One pipeline function for the CLI and the service

**Decision**: Move the body of `cli._analyze_and_store` into `graphora/pipeline/run.py` as
`run_pipeline(source, limits, store, on_stage) -> PipelineResult`. It resolves the ref (GitHub), checks
`find_reusable`, fetches, analyzes, adds skipped entries and calls `Store.put`, calling `on_stage(stage)` at
each step. `graphora analyze --store` calls it with a no-op `on_stage` and keeps its output byte for byte.
Exceptions stay the existing ones (`BadInput`, `RemoteError`, `LimitExceeded`, `UnsafeArchive`,
`InvalidArchive`, `StoreUnavailable`, `InvalidAnalysis`).

**Rationale**: FR-013 (same result as the CLI) and FR-020 (no second implementation) are met by
construction: both paths run the same code. The CLI-specific parts (info lines, exit statuses) stay in the
CLI.

**Alternatives considered**: calling `graphora analyze` as a subprocess from the service (parses stderr to
get stages and errors; slow; a second process model); a parallel implementation in the service (drifts).

## R3. One store connection per running job

**Decision**: The service keeps its read `Store` for the API. Each running job opens its own `Store` from
the same database URL and closes it when the job ends. `create_app(store, runner=None)` keeps the 005
signature; `serve` builds a `JobRunner(database_url, …)` and passes it in.

**Rationale**: `Store` serializes all calls on its one connection (`self._lock`). A job's `put` is a long
transaction (blob inserts for up to 50 MB); on the shared connection it would block every API read for its
whole duration. Opening the job's connection lazily also gives FR-004/acceptance 4 of US4: a dead database
fails only that job with `store`.

**Alternatives considered**: a connection pool (`psycopg_pool`, new dependency; one job at a time does not
need a pool); sharing the API connection (blocks reads, above).

## R4. Upload: raw request body, not multipart

**Decision**: `POST /api/v1/jobs/zip?name=<file name>` with the archive as the raw body
(`Content-Type: application/zip` or `application/octet-stream`). The handler streams the body to a file in
the job's folder, counting bytes, and stops with `413 limit` once `max_archive_bytes` is passed. A
`Content-Length` above the limit is rejected before reading anything.

**Rationale**: FR-017 (stop as soon as the limit is passed) is a simple counter over `request.stream()`.
Multipart parsing in FastAPI needs the new `python-multipart` dependency and spools the whole part before the
handler runs, so the limit could only be checked after the full upload. A raw body is also the easiest for
`curl --data-binary @app.zip` and for the future frontend (`fetch(url, {body: file})`).

**Alternatives considered**: `multipart/form-data` (above); base64 inside JSON (+33 % size, whole body in
memory).

## R5. Endpoints and status codes

**Decision** (full shapes in [contracts/http-api.md](contracts/http-api.md)):

| Operation | Endpoint | Success |
|---|---|---|
| Start from a GitHub link | `POST /api/v1/jobs` with JSON `{"github": "<link>", "ref": …, "limits": {…}}` | `202` + job status |
| Start from a ZIP upload | `POST /api/v1/jobs/zip?name=<name>[&max_…=<n>]`, raw body | `202` + job status |
| Read a job | `GET /api/v1/jobs/{id}` | `200` + job status |

New error kinds: `too_many_jobs` (`429`) when the queue is full, `limit` (`413`) for an upload over the size
limit. `405` keeps its kind; its message becomes `method not allowed` because the API is no longer GET-only.

**Rationale**: "job" is what the client polls; the analysis itself is still read through 005's
`/repositories`, `/graph`, `/file`, so nothing there changes (FR-022). `202 Accepted` is the standard answer
for work that continues after the response. The GitHub body is JSON so the link is never put in a URL that
might be logged with query strings.

**Alternatives considered**: `POST /api/v1/repos` from `project-context.md` § 5 (that sketch predates the
005 resource names; the job, not the repository, is created); one endpoint for both inputs (mixes a JSON body
with a binary one).

## R6. Job status body and determinism

**Decision**: The status is a JSON object with sorted keys and no whitespace (the 005 `json_bytes` rule):
`id`, `stage`, `source`, `limits`, `result` (or `null`), `error` (or `null`). No timestamps, no queue
position, no elapsed time. For a given job state the body is byte-identical (FR-009).

**Rationale**: FR-009 and the 005 FR-016 rule for API bodies. Queue position and elapsed time change while
nothing about the job changes, so polling would never see stable bytes. The stage already tells the client
whether to keep polling.

## R7. Time limit, stopping and stages

**Decision**: A `JobDeadline` (subclass of `Deadline`) is created when the job leaves the queue (FR-016). Its
`check()` also raises `Interrupted` when the runner is stopping. On `serve` shutdown the runner stops taking
jobs, marks queued jobs `failed/interrupted`, sets the stop flag and joins its threads; a running job stops
at its next deadline check, and its `with` blocks remove its folder and roll back its transaction.

Stages are set by `on_stage` from the pipeline: `resolving` before `resolve_sha` (GitHub only), `fetching`
before download/extraction, `analyzing` when the snapshot folder is ready, `storing` before `Store.put`.
A GitHub reuse goes `resolving → done` directly. A stage setter refuses to move backwards (FR-006).

**Rationale**: `Deadline.check()` is already called in the walk, in the analysis loop and per chunk in the
extraction loops, which read the download stream, so the stop flag needs no new hooks. Interrupted jobs are never visible after the restart (FR-012);
the kind exists so a client polling during shutdown gets a clear answer.

## R8. Job folders and cleanup after a crash

**Decision**: The runner owns one work folder, default `<system temp>/graphora-jobs`, set with
`--work-dir`. At start it takes an exclusive `flock` on `<work-dir>/.lock`; if another service holds it,
`serve` exits with a clear error. Holding the lock, it removes every other entry in the folder (leftovers of
a killed service, FR-018). Each job uses `<work-dir>/<job id>/`: the upload is written there and
`fetch_snapshot(..., workdir=…)` creates its temp folder inside it. The job folder is removed when the job
ends, in a `finally`.

`fetch_snapshot` gets one optional parameter `workdir: Path | None = None` passed to
`tempfile.TemporaryDirectory(dir=…)`. `None` keeps the 002 behaviour.

**Rationale**: cleaning `graphora-*` folders in the shared system temp would delete folders of CLI runs that
are still going. A private folder guarded by a lock is safe to wipe.

**Alternatives considered**: no cleanup (violates FR-018); a PID file (stale after a crash, racy); cleaning
by age (deletes a long running CLI analysis).

**Ownership**: `ingest/fetch.py` is Anna's module (`team-workflow.md`); the PR requests her review for the
one-parameter change.

## R9. Input checks before a job exists

**Decision**: Before a job is created (FR-004):

- GitHub: `parse_source(link, ref)` — the CLI's own parser and messages. Only a value starting with a scheme
  is accepted; anything else is `bad_request` `not a GitHub repository link: …`, so a local path or ZIP path
  can never reach `parse_source`'s file-system branch (FR-003).
- ZIP name: non-empty, at most 255 bytes, no `/`, `\` or NUL, not `.` or `..`; the repository name (name
  without the last extension) must be 1–300 characters (005 FR-002).
- ZIP body: received fully under the size limit (R4), then its first 4 bytes must be a ZIP signature
  (`parse_source`'s rule) — otherwise `bad_request` `not a ZIP archive: <name>`.
- Limits: each given key is one of the six limit names, an integer (seconds may be a number) ≥ 1 and ≤ the
  server's value; otherwise `bad_request` naming the key.

Messages that mention CLI flags (`--ref given twice`) are reworded only where the flag does not exist over
HTTP: the API maps `--ref` → `ref`; the reason is unchanged.

## R10. Duplicate submissions

**Decision**: The runner keeps an index from a dedup key to the id of a job that is not finished. The key for
GitHub is `(owner, repo, ref or "", limits)`; ZIP uploads are never deduplicated before the analysis (two
uploads have no cheap identity before extraction), and the store already makes two identical uploads end
with one analysis (005 FR-009, acceptance 4 of US3). The entry is removed when the job ends.

**Rationale**: FR-011 and SC-004. Including the limits keeps "same request" literal: a job with lower limits
might fail where the other succeeds.

## R11. Failure kinds and messages

**Decision**: one mapping, used only by the service:

| Exception | `kind` | Message |
|---|---|---|
| `RemoteError` | `remote` | its message (already names the repository, ref or host) |
| `LimitExceeded` | `limit` | the CLI template with the API key name: `file limit exceeded: at least 5001 files > max_files 5000` |
| `UnsafeArchive`, `InvalidArchive` | `archive` | its message (paths inside the archive only) |
| `StoreUnavailable` | `store` | `store unavailable` (the reason goes to the server log: it may contain the URL) |
| `InvalidAnalysis` | `invalid` | `cannot store the analysis: <reason>` |
| `Interrupted` | `interrupted` | `the service is stopping` |
| anything else | `internal` | `internal error`; the traceback goes to the server log |

The limit message templates move from `cli/__init__.py` to `pipeline/messages.py`, parameterized by the
limit's display name, so the CLI keeps `--max-files` and the API says `max_files` (FR-022, FR-008).

## R12. Testing approach

**Decision**:

- Unit, no database: `JobRunner` with a stub pipeline function — FIFO order, `workers` bound, queue full,
  dedup, stage order, stop/interrupt, status bytes stable; input checks (R9).
- Integration, `db`: FastAPI `TestClient` + real `JobRunner` + `fake_github`. Every failure kind (US4),
  reuse with zero downloads (US2), upload limits and hostile archives from `tests/archives.py` (US3),
  work-folder cleanup, CLI unchanged.
- Golden, `db`: every fixture as a GitHub stand-in tarball and as a ZIP upload; stored graph equals the
  CLI `--store` bytes; run three times (SC-001).
- A `wait_for(client, id)` helper polls `GET /jobs/{id}` with a 30 s cap; no fixed sleeps.

**Rationale**: matches 005's split (unit / `db` integration / golden) and keeps the suite offline (SC-007).
