# Feature Specification: Analysis Storage and HTTP API

**Feature Branch**: `005-storage-http-api`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "хранилище и API" (storage and API; feature 005 in `docs/product/team-workflow.md`)

## Clarifications

### Session 2026-11-05

- Q: Does import over HTTP (GitHub link or ZIP upload) belong to this slice? → A: No. Per the team plan,
  005 is storage and the API, and 007 is the end-to-end pipeline. In 005 the store is filled by the CLI and
  the HTTP API is read-only. Import over HTTP, background jobs and progress are feature 007.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An analysis is kept and reused, not recomputed (Priority: P1)

A developer analyzes a repository once. The resulting graph and the text of the snapshot's files are kept
by Graphora under the pair (repository, snapshot id). Later, asking for the same repository at the same
commit returns the stored graph instead of downloading and analyzing again. Stored analyses survive a
restart of the service.

**Why this priority**: Every later consumer (map UI, graph queries over HTTP, MCP server, claim verifier,
agents) needs a graph and the file text of a fixed snapshot after the temporary snapshot folder is gone.
The verifier must check "this line of this file at this commit contains this symbol" without fetching the
repository again. Reuse by commit is also the main promise of a commit-pinned graph: the same commit is
analyzed once.

**Independent Test**: Run `graphora analyze` with the new store option on each fixture repository, restart,
read the graph back and compare it byte for byte with the plain CLI output for the same input. Run it a
second time on the same GitHub commit and observe that no archive is downloaded.

**Acceptance Scenarios**:

1. **Given** an empty store, **When** a fixture repository is analyzed with the store option, **Then** the
   store holds one analysis for (repository name, snapshot id), and the stored graph is byte-identical to
   what `graphora analyze` prints for the same input.
2. **Given** a stored analysis of `github.com/o/r` at commit `S`, **When** `github.com/o/r` is requested at a
   ref that points to `S` and the current schema and extractor versions match the stored ones, **Then** the
   stored analysis is returned and the repository archive is not downloaded.
3. **Given** a stored analysis made with an older schema version or older extractor versions, **When** the
   same repository and snapshot are analyzed again, **Then** the analysis is recomputed and replaces the old
   one, so the pair (repository, snapshot id) still has exactly one analysis.
4. **Given** stored analyses, **When** the service is stopped and started again, **Then** every stored
   analysis and every stored file is still available unchanged.
5. **Given** an analysis that fails or is interrupted part-way, **When** the store is read, **Then** no
   partial analysis is visible, and any earlier analysis of the same pair is unchanged.

---

### User Story 2 - Read graphs and source files over HTTP (Priority: P1)

The frontend (and later the MCP server and agents in other processes) reads stored data over HTTP: which
repositories exist, which snapshots each one has, the full graph of a snapshot, and the text of any file in
that snapshot with line numbers, for the source viewer and provenance card.

**Why this priority**: The frontend team builds against this API (`docs/product/project-context.md` § 5).
Without it the map and the provenance card cannot show real data.

**Independent Test**: Start the service on a store filled from the fixture repositories and request each
read operation. Compare the graph with the CLI output and the file text with the file on disk.

**Acceptance Scenarios**:

1. **Given** a store with fixtures `py-flat` and `ts-app`, **When** the client lists repositories, **Then**
   it gets both names in sorted order, each with its stored snapshot ids.
2. **Given** a stored snapshot, **When** the client requests its graph, **Then** the response body is
   byte-identical to the stored graph document, and two requests return identical bytes.
3. **Given** a stored snapshot that contains `src/a.py`, **When** the client requests that file, **Then** it
   gets the exact text that was analyzed, and requesting lines 3–5 returns exactly those lines with their
   numbers.
4. **Given** a stored snapshot, **When** the client requests a path that is not a file of that snapshot
   (for example `../../etc/passwd`, `/etc/passwd`, a skipped folder or a file of another snapshot), **Then**
   it gets a "not found" answer and nothing outside the store is read.
5. **Given** a file of the snapshot that is binary or not valid UTF-8, **When** the client requests it,
   **Then** it gets a clear answer that the file has no text content, not garbled text.
6. **Given** a repository name or snapshot id that is not stored, **When** the client asks for it, **Then**
   it gets a "not found" answer that names what was missing.

---

### Edge Cases

- Two CLI runs store the same repository and commit at the same time: exactly one analysis is stored, and
  both runs report success.
- Two different ZIP files with the same file name: they share the repository name and are told apart by
  their `content:` snapshot ids.
- The same ZIP analyzed twice: the second run produces the same snapshot id, and no second copy is stored.
- The store is written by the CLI while the API is serving reads: readers see either the old state or the
  complete new analysis, never a mix.
- A local folder with uncommitted changes is stored under its `<sha>+dirty:<hash>` snapshot id; after a new
  change it is a different snapshot.
- A file path in the request uses a different case, a trailing slash, `./` or `\`: it is not normalized into
  a match; only exact stored paths are found.
- A line range outside the file (start past the end, start after end, zero or negative numbers) is a
  request error, not an empty success.
- The store is unavailable when the service starts or during a request: the service reports a clear
  error and does not fall back to analyzing without storing.
- A stored graph document is checked against `schema/graph.schema.json` before it is stored; a document
  that fails the check is not stored.
- A repository with zero analyzable files still produces a stored analysis with an empty graph and a
  coverage report.

## Requirements *(mandatory)*

### Functional Requirements

**Storage**

- **FR-001**: The system MUST store each analysis under the pair (repository name, snapshot id). The pair
  MUST have at most one stored analysis.
- **FR-002**: Repository names MUST follow the rules of feature 002: `github.com/<owner>/<repo>` in lower
  case for GitHub, the file name without its last extension for ZIP, and the folder name for a local folder.
- **FR-003**: A stored analysis MUST contain the graph document exactly as serialized (the same bytes the
  CLI writes), the schema version, the extractor names and versions, and the run's warnings.
- **FR-004**: A stored analysis MUST contain the text of every file listed in the coverage report of its
  graph. Files that are binary or not valid UTF-8 MUST be recorded as having no text content. Files outside
  the coverage report (skipped folders, symlinks) MUST NOT be stored.
- **FR-005**: The stored graph and file text MUST NOT be changed after they are stored, except by
  replacing the whole analysis under FR-007.
- **FR-006**: An analysis MUST become visible all at once: the graph and all its files together, or nothing.
  A failed or interrupted run MUST leave no visible part and MUST NOT change an earlier stored analysis.
- **FR-007**: When the same pair is analyzed again, a stored analysis MUST be reused if its schema version
  and extractor versions equal the current ones. Otherwise it MUST be recomputed and the new analysis MUST
  replace the old one.
- **FR-008**: For a GitHub source, the system MUST resolve the ref to a commit SHA first and MUST NOT
  download the archive when a reusable analysis for that commit exists.
- **FR-009**: Concurrent analyses of the same pair MUST result in exactly one stored analysis.
- **FR-010**: Stored data MUST persist across restarts of the service and the CLI.
- **FR-011**: The CLI `analyze` command MUST get an option to store its result. Without the option its
  output, exit codes and messages MUST stay exactly as today.

**HTTP read API**

- **FR-012**: The API MUST list stored repositories, sorted by name, each with its stored snapshot ids
  sorted.
- **FR-013**: The API MUST return the graph document of a stored (repository, snapshot id) pair as the exact
  stored bytes.
- **FR-014**: The API MUST return the text of a file of a stored snapshot by its exact path as written in
  the coverage report, either whole or as an inclusive line range, with line numbers.
- **FR-015**: The API MUST answer file requests only from stored data. It MUST NOT read the file system of
  the server or of any analyzed source to answer them, so a path outside the snapshot cannot be reached.
- **FR-016**: Every API response MUST be deterministic: the same stored data and the same request give a
  byte-identical body. Lists MUST be sorted; bodies MUST NOT contain timestamps or other values that change
  between requests.
- **FR-017**: Errors MUST be reported with distinct kinds — bad request, not found, store unavailable — and
  a message naming what failed. Error bodies MUST NOT include server file paths or internal traces.
- **FR-018**: The API MUST be read-only. It MUST NOT offer any operation that starts an analysis, runs
  analyzed code, changes or deletes stored data, or reads anything outside the store. Import over HTTP is
  feature 007.

**General**

- **FR-019**: Graph queries (cycles, reverse dependencies, impact, centrality) MUST NOT be implemented in
  the API or the store. They belong to the graph query layer (feature 004) and are exposed over HTTP in a
  later slice.
- **FR-020**: By default the service MUST accept connections only from the same machine.

### Key Entities

- **Repository**: a named source of snapshots (`github.com/o/r`, a ZIP name or a folder name). Has zero or
  more stored analyses.
- **Analysis**: the result of one analysis of one snapshot of one repository. Identified by (repository
  name, snapshot id). Holds the graph document bytes, schema version, extractor versions and warnings.
- **Stored file**: the text of one file of an analyzed snapshot, identified by (repository name, snapshot
  id, path). Either has text content or is marked as having none (binary or not UTF-8).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of fixture repositories, the graph read back from the store and over the API is
  byte-identical to the plain CLI output for the same input, on every one of 3 repeated runs.
- **SC-002**: Analyzing an already stored GitHub commit again with the store option finishes in under
  2 seconds, with zero archive downloads.
- **SC-003**: After a restart, 100% of stored analyses and files are returned unchanged.
- **SC-004**: The graph of a stored repository at the default limits (5,000 files) is returned in under
  2 seconds, and any single file or line range in under 0.5 seconds, on a typical developer laptop.
- **SC-005**: 0 of the hostile requests in the test suite (path traversal, absolute paths, paths of skipped
  folders or of other snapshots) return data from outside the requested stored snapshot, and 0 requests
  change stored data.
- **SC-006**: 0 partial analyses are visible after any failed or interrupted run in the test suite, and no
  temporary files remain.
- **SC-007**: All tests that existed before this feature pass unchanged, and the full suite passes with the
  network disabled.

## Assumptions

- This is feature 005 from the team plan (`docs/product/team-workflow.md`). Graph queries are feature 004;
  the end-to-end pipeline (import over HTTP from a GitHub link or ZIP upload, background jobs, progress,
  wiring the UI and agents) is feature 007, which will reuse this store. Agent questions (`/ask`) are
  feature 010.
- In this slice the store is filled only by the CLI. The frontend reads analyses prepared in advance.
- The service is used by one person or team on a local machine or a trusted network. Accounts, login and
  access control are out of scope; FR-020 keeps the service local by default.
- The graph document format (`schema/graph.schema.json`) does not change in this slice.
- Deleting analyses, listing history over time and storage quotas are out of scope. The store grows until
  cleared by hand.
- File text is stored for the whole coverage report (not only analyzed files) so the viewer can show
  configuration files such as `package.json` and `tsconfig.json` that edges and coverage refer to. The
  existing size limits already bound how much is stored per analysis.
- Different ZIP files with the same name share a repository name; their snapshot ids keep them apart. This
  follows the naming rule of feature 002 and is acceptable for the MVP.
- The repository name of a stored analysis is not written into the graph document; it is part of the store
  key only.
