# Feature Specification: End-to-End Pipeline (Import and Analyze over HTTP)

**Feature Branch**: `010-end-to-end-pipeline`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "pipeline end-to-end" (feature 010 in `docs/product/team-workflow.md`, issue #23).
Scope agreed before specifying: start an analysis over HTTP from a GitHub link or an uploaded ZIP, run it
in the background, report its progress, reuse a stored analysis of the same commit, and make the result
available through the existing read API and MCP server.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Import a GitHub repository over HTTP and get its graph (Priority: P1)

A user (later, the web UI) sends a GitHub link, optionally with a ref, to the running service. The service
answers at once with an analysis job and does the work in the background: resolve the ref to a commit,
download, detect languages, analyze, store. The user polls the job and sees which stage it is in. When the
job is done, its status names the stored repository and snapshot id, and the graph and files are readable
through the existing read API and can be opened by the MCP server, with no CLI step in between.

**Why this priority**: Today the store is filled only by the CLI (feature 005), so the frontend can show
only repositories prepared by hand. This story is the pipeline: one request turns a link into a stored,
queryable graph. Every later consumer (map UI, `/ask`, agents, HTTP bridge) starts here.

**Independent Test**: Start the service with an empty store and a local stand-in for GitHub serving a
fixture repository archive. Submit the link, poll until done, read the graph through the read API and
compare it byte for byte with `graphora analyze --store` output for the same commit.

**Acceptance Scenarios**:

1. **Given** a running service and an empty store, **When** the user submits `https://github.com/o/r`,
   **Then** the answer comes back immediately with a job id and the stage `queued` or later, before the
   download finishes.
2. **Given** a submitted job, **When** the user asks for its status repeatedly, **Then** the stages are
   reported in order (`queued` → `resolving` → `fetching` → `analyzing` → `storing` → `done`) and never go
   back.
3. **Given** a job that reached `done`, **When** the user reads its status, **Then** it names the repository
   (`github.com/o/r`), the snapshot id (the commit SHA), whether the analysis was newly stored or reused,
   and counts of analyzed files, edges and unresolved edges.
4. **Given** a `done` job, **When** the graph of its repository and snapshot is requested through the read
   API, **Then** it is byte-identical to what `graphora analyze --store` stores for the same commit.
5. **Given** a `done` job, **When** the MCP server is started in store mode with the repository and snapshot
   from the job status, **Then** it answers graph questions about that snapshot.

---

### User Story 2 - A commit that is already stored is not analyzed again (Priority: P1)

The user submits a GitHub link at a ref that points to a commit already stored with the current schema and
extractor versions. The job resolves the ref, finds the stored analysis and finishes without downloading or
analyzing anything. Two users who submit the same repository and ref at the same time share one job.

**Why this priority**: Reuse by commit is the main promise of a commit-pinned graph (feature 005, FR-007 and
FR-008). Over HTTP it also protects the machine: repeated clicks in a UI must not start repeated downloads.

**Independent Test**: Submit the same link twice in a row and once more while a job for it is still running;
count archive downloads in the GitHub stand-in.

**Acceptance Scenarios**:

1. **Given** a stored, reusable analysis of `github.com/o/r` at commit `S`, **When** the user submits
   `github.com/o/r` at a ref pointing to `S`, **Then** the job reaches `done` with "reused", and no archive
   is downloaded.
2. **Given** a job for `github.com/o/r` at ref `main` that is not finished, **When** the same link, ref and
   limits are submitted again, **Then** the answer is the same job id, and only one download and one analysis
   happen.
3. **Given** a stored analysis made with older extractor versions, **When** the same commit is submitted,
   **Then** the job downloads, analyzes and replaces it, and the status says "replaced".

---

### User Story 3 - Upload a ZIP archive over HTTP (Priority: P2)

The user uploads a ZIP archive of a repository instead of giving a link. The same job flow applies: the
archive is checked against the size limit while it is received, extracted safely in the background,
analyzed and stored under the archive's file name and its `content:` snapshot id.

**Why this priority**: ZIP is the second import path of the MVP (private code, no GitHub). It is P2 because
it reuses the whole job flow of User Story 1 and differs only in how the input arrives.

**Independent Test**: Upload each fixture repository as a ZIP, wait for `done`, and compare the stored graph
with `graphora analyze <file.zip> --store` output. Upload the hostile archives from the 002 test suite and
check each fails with the same reason the CLI gives.

**Acceptance Scenarios**:

1. **Given** a fixture repository packed as `app.zip`, **When** it is uploaded, **Then** the job reaches
   `done` with repository `app` and a `content:` snapshot id equal to the CLI's for the same file.
2. **Given** an upload larger than the archive size limit, **When** it is sent, **Then** it is rejected with
   the limit named, as soon as the limit is passed, and no job is created.
3. **Given** an archive with path traversal, a zip bomb or an escaping symlink, **When** it is uploaded,
   **Then** the job ends `failed` with the same reason the CLI reports, and nothing is extracted outside
   the job's temporary folder.
4. **Given** the same archive uploaded twice, **When** both jobs finish, **Then** the store holds one
   analysis for that repository and snapshot.

---

### User Story 4 - Failures are reported clearly and leave no trace (Priority: P2)

A job can fail: the link is not a GitHub repository, the ref does not exist, GitHub is unreachable, a limit
is exceeded, the archive is unsafe, the store is down. The user sees `failed` with an error kind and a
message naming what failed, worded like the CLI's message for the same case. Nothing partial is stored, and
the job's temporary files are removed.

**Why this priority**: Public repositories are untrusted input (constitution I). A UI needs to tell "bad
link" from "too large" from "try again later" to show the right message.

**Independent Test**: Submit one input for each failure kind against the GitHub stand-in and a store that
can be stopped; check the status, the store and the temporary folder after each.

**Acceptance Scenarios**:

1. **Given** a malformed link or an invalid ref name, **When** it is submitted, **Then** it is rejected at
   once as a bad request and no job is created.
2. **Given** a well-formed link to a repository or ref that does not exist, **When** the job runs, **Then**
   it ends `failed` with the kind `remote` and a message naming the repository or ref.
3. **Given** a repository larger than the file, size or time limit, **When** the job runs, **Then** it ends
   `failed` with the kind `limit` and a message naming the limit and its value.
4. **Given** the store is unavailable, **When** a job reaches `storing` (or `resolving`, where the store is
   checked for reuse), **Then** it ends `failed` with the kind `store`.
5. **Given** any failed job, **When** the store and the server's temporary folder are inspected, **Then** no
   partial analysis is visible and no files of that job remain.

---

### Edge Cases

- The service is stopped while jobs are queued or running: stored analyses are unchanged, no partial
  analysis is visible, temporary files of those jobs are removed on the next start, and their job ids are
  unknown after the restart.
- Many jobs are submitted at once: at most the configured number run at the same time (default 1); the
  rest wait as `queued` in submission order.
- The queue is full (default 20 waiting jobs): new submissions are rejected with a "too many jobs" answer,
  not queued without bound.
- An unknown or malformed job id is asked for: "not found", naming the id.
- A link with `/tree/<ref>` and a separate ref as well: rejected as a bad request, as in the CLI.
- The same repository at two different refs that point to the same commit: two jobs may run, but the store
  ends with exactly one analysis for that commit (feature 005, FR-009).
- A ref that moves while a job is running (new commit pushed to `main`): the job keeps the commit it
  resolved first.
- An upload that is not a ZIP (wrong signature) or is cut off: rejected or failed with the kind `archive`,
  as in the CLI.
- An upload with an empty or unsafe file name (`../x.zip`, a name with `/` or `\`): rejected as a bad
  request; only the base name is ever used for the repository name.
- A request asking to analyze a local folder or a server file path: not offered; the only inputs are a
  GitHub link and an uploaded archive.
- Client-supplied limits higher than the server's limits: rejected as a bad request; lower limits are
  accepted.
- A finished job's status is asked for many times: the answer is the same bytes every time.

## Requirements *(mandatory)*

### Functional Requirements

**Starting an analysis**

- **FR-001**: The service MUST offer an operation that starts an analysis from a GitHub repository link with
  an optional ref, accepted under the same rules as the CLI (feature 002).
- **FR-002**: The service MUST offer an operation that starts an analysis from an uploaded ZIP archive and
  its file name. The repository name MUST follow feature 002: the base file name without its last
  extension.
- **FR-003**: The service MUST NOT accept a local folder, a server file path or any URL other than a GitHub
  repository link as input.
- **FR-004**: Input that can be checked without network access (link syntax, ref syntax, file name,
  archive signature, client limits) MUST be checked before a job is created; bad input MUST be rejected as
  a bad request with a message giving the same reason as the CLI.
- **FR-005**: Starting an analysis MUST answer without waiting for the download or the analysis, with a job
  id and the job's current status.

**Jobs and progress**

- **FR-006**: Each job MUST report one stage at a time from `queued`, `resolving` (GitHub only), `fetching`,
  `analyzing`, `storing`, and one end state, `done` or `failed`. Stages MUST only move forward.
- **FR-007**: A `done` job MUST report the repository name, the snapshot id, whether the analysis was
  `stored`, `replaced` or `reused`, and the counts of analyzed files, edges and unresolved edges of the
  stored graph.
- **FR-008**: A `failed` job MUST report an error kind — `remote`, `limit`, `archive`, `store`, `invalid`
  (the analysis failed the schema check before storing), `interrupted` (the service is stopping) or
  `internal` (an unexpected error, with a fixed message) — and a message giving the same reason as the CLI
  for the same failure; a limit message names the limit and its value. Messages MUST NOT include server file
  paths or internal traces.
- **FR-009**: The service MUST let the client read a job's status by its id. Job ids MUST NOT be guessable
  from other job ids. For a given job state the status body MUST be byte-identical on every request and
  MUST NOT contain timestamps.
- **FR-010**: At most a configured number of jobs (default 1) MUST run at the same time; others wait in
  submission order. At most a configured number of jobs (default 20) MAY wait; beyond that, new
  submissions MUST be rejected with a distinct "too many jobs" answer.
- **FR-011**: Submitting a GitHub link, ref and limits identical to those of a job that is not finished MUST
  return that job instead of creating a new one. The same link and ref with different limits is a new job,
  because it may end differently.
- **FR-012**: Finished jobs MUST stay readable until the service stops. Job state is not required to
  survive a restart.

**Running the analysis**

- **FR-013**: A job MUST produce the same stored analysis as `graphora analyze <same source> --store` with
  the same limits: byte-identical graph, same snapshot id, same repository name, same warnings.
- **FR-014**: A job MUST follow the reuse and replace rules of feature 005 (FR-007, FR-008): for GitHub the
  ref is resolved first, and a reusable stored analysis ends the job as `reused` with no download.
- **FR-015**: The ingest and analysis limits (files, bytes, time, archive size, extracted size, entries) MUST
  apply to every job. Server defaults MUST equal the CLI defaults and MAY be changed when the service is
  started. A client MAY ask for lower limits for its job, never higher ones.
- **FR-016**: The time limit MUST bound the whole job from leaving the queue to its end state; time spent
  waiting in the queue does not count.
- **FR-017**: An uploaded archive MUST be rejected as soon as it exceeds the archive size limit while being
  received, without reading the rest.
- **FR-018**: Each job MUST use its own temporary folder. Uploaded archives and extracted snapshots MUST be
  removed when the job ends, whatever the outcome; leftovers of jobs cut off by a stop MUST be removed at
  the next start.
- **FR-019**: A failed or interrupted job MUST leave no visible part in the store and MUST NOT change an
  earlier stored analysis (feature 005, FR-006).
- **FR-020**: Analyzed code MUST NOT be executed, and project and configuration files MUST be read as data
  only (constitution I). The pipeline MUST reuse the existing ingest, analysis and store functions and MUST
  NOT add a second implementation of any of them.

**Consumers**

- **FR-021**: The graph and files of a `done` job MUST be readable through the existing read API (feature
  005) and usable by the MCP server in store mode (feature 006) using the repository and snapshot from the
  job status, with no other step.
- **FR-022**: The existing read operations, the CLI and the MCP server MUST keep their current behaviour,
  output and messages.

**General**

- **FR-023**: Apart from starting analyses (which adds or replaces stored analyses under the 005 rules),
  the service MUST NOT offer any operation that changes or deletes stored data. This replaces feature 005
  FR-018 ("the API MUST be read-only"); every agent and MCP tool stays read-only (constitution I).
- **FR-024**: By default the service MUST accept connections only from the same machine (feature 005,
  FR-020).

### Key Entities

- **Analysis job**: one request to analyze one source. Has an id, the source (GitHub link and ref, or
  archive name), the limits it runs with, a stage, and either a result (repository, snapshot id, action,
  counts) or a failure (kind, message). Lives in the running service only.
- **Job queue**: the ordered list of jobs waiting to run, bounded in length, with a bounded number of jobs
  running at once.
- **Analysis** and **Stored file**: as defined in feature 005; a `done` job points to exactly one analysis.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of fixture repositories, submitted both as a GitHub link (through a local stand-in)
  and as an uploaded ZIP, the stored graph after `done` is byte-identical to the CLI `--store` result, on
  each of 3 repeated runs.
- **SC-002**: Starting an analysis answers in under 1 second, whatever the repository size.
- **SC-003**: Submitting an already stored GitHub commit reaches `done` in under 2 seconds with zero archive
  downloads.
- **SC-004**: Ten identical submissions of the same link and ref while the first is running cause exactly
  one download and one analysis.
- **SC-005**: For each failure kind in the test suite, 100% of jobs end `failed` with the expected kind and
  a message giving the CLI's reason, with no partial analysis stored and no temporary files left.
- **SC-006**: 0 of the hostile archives from the 002 test suite write any file outside their job's
  temporary folder when uploaded.
- **SC-007**: All tests that existed before this feature pass unchanged, and the full suite passes with no
  connection outside the local machine (the local test database and the GitHub stand-in are the only
  connections allowed).

## Assumptions

- This is feature 010 from the team plan (`docs/product/team-workflow.md`), originally numbered 007; numbers
  007–009 went to C# analysis. It completes what feature 005 left out: import over HTTP, background jobs and
  progress (005 spec, Clarifications and Assumptions).
- The service is used by one person or team on a local machine or a trusted network. Accounts, login,
  access control and per-user quotas are out of scope; FR-024 keeps the service local by default.
- Job state is kept only while the service runs. A durable job history, cancelling a job, listing all jobs,
  pushing progress to the client (instead of polling) and progress finer than the stage are out of scope.
- Local folders are not accepted over HTTP, so the server never reads paths chosen by a client. Local
  folders stay a CLI input.
- Wiring the frontend to these operations is the HTTP bridge feature (015). Agents and `/ask` (012, 013)
  will read analyses produced here.
- The graph document format (`schema/graph.schema.json`) does not change in this slice.
- The GitHub stand-in used by tests is the same kind of local fake used by the 002 and 005 tests; no test
  reaches the real GitHub.
