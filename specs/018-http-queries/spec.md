# Feature Specification: Graph Queries over HTTP

**Feature Branch**: `018-http-queries`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "018 http queries, issue #38" — the graph questions that the CLI and the MCP server
already answer (`impact`, `cycles`, `dependents`, `dependencies`, `neighbors`, `key_files`, `definitions`,
`overview`, `projects`) become available over the HTTP API for stored snapshots, so the web UI of rounds 6–7 can
show impact mode, the cycles list, the neighbours and dependents panel, symbol search and the header numbers
(`docs/demo/README.md` § 2, § 4, § 5, § 8) without computing anything itself (constitution VII).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Impact and neighbours of a selected file (Priority: P1)

A developer opens a stored snapshot in the web UI and clicks a file. The UI asks the HTTP API what depends on the
file (`impact`), what it imports and what imports it (`neighbors`, `dependencies`, `dependents`), and highlights
the answer on the graph. Every link in the answer cites `file:line` and its confidence, exactly as the CLI and
the MCP server give it, so the UI can draw facts and likely links differently.

**Why this priority**: Impact mode and the side panel of a selected node are the main screens of the demo
(§ 4, § 2, § 5) and the first thing the frontend slice needs. Without them the UI can only draw the raw graph.

**Independent Test**: Store a fixture snapshot, request `impact`, `neighbors`, `dependencies` and `dependents` of
a known file over HTTP, and compare each response body byte for byte with `graphora query <graph> <question>
<target> --format json` run with the same options and the same limit.

**Acceptance Scenarios**:

1. **Given** a stored snapshot and a file path in it, **When** its impact is requested over HTTP, **Then** the
   answer lists every file that depends on it directly or through other files, nearest first, each with its
   chain of import links, and the body equals the CLI JSON answer for the same options.
2. **Given** the same request with `max_depth`, `include_type_only=false`, `follow_barrels=true` or
   `level=project`, **When** it is answered, **Then** the option has the same effect as in the CLI and MCP.
3. **Given** a target that is not in the snapshot, is skipped, is `detected_only`/`not_code`, or is an ambiguous
   package name, **When** it is requested, **Then** the answer is "not found" and the message says why (the same
   reason the CLI gives); no partial answer is returned.
4. **Given** a `dependents` request with `symbol`, **When** it is answered, **Then** only imports of that name are
   listed, as in the CLI.
5. **Given** an answer with more items than the limit, **When** it is returned, **Then** it holds at most the
   limit, with the total and a truncated flag.

---

### User Story 2 - Whole-snapshot answers: cycles, key files, overview, projects (Priority: P1)

The UI shows the cycles list (§ 8), the header numbers (files, languages, unresolved imports) and the most
depended-on files of a stored snapshot. For a C# repository it lists the projects. These answers do not need a
target; the UI fetches them when the snapshot is opened.

**Why this priority**: The cycles screen and the header are part of the first frontend slice, and the overview is
the honest statement of what the graph covers and what it cannot see (constitution IV).

**Independent Test**: For each stored fixture snapshot, request `cycles`, `key_files`, `overview` and `projects`
over HTTP and compare each body with the CLI JSON answer for the same graph.

**Acceptance Scenarios**:

1. **Given** a stored snapshot with import cycles, **When** cycles are requested, **Then** each group is listed with
   one example cycle of import lines and the type-only mark, equal to the CLI answer.
2. **Given** a stored snapshot, **When** the overview is requested, **Then** it states the snapshot, languages,
   analyzed and skipped files and unresolved imports, equal to the CLI answer.
3. **Given** a repository without C# projects, **When** projects are requested, **Then** the answer is valid and
   empty, not an error.
4. **Given** the same request made twice, **When** the answers are compared, **Then** they are byte-identical.

---

### User Story 3 - Find a symbol by name (Priority: P2)

A developer types a class or function name in the UI search box. The UI asks the HTTP API where a symbol with that
exact name is defined and shows the file, line and kind of each definition, so the developer can jump to the file
and then ask its impact.

**Why this priority**: Search is part of the first slice but only useful once impact and the panel work; it is a
single question with one parameter.

**Independent Test**: Request `definitions` for a known class name of a fixture and for a name that does not
exist; compare with the CLI answers.

**Acceptance Scenarios**:

1. **Given** a name defined in two files, **When** definitions are requested, **Then** both are listed with file,
   line, kind and full name, equal to the CLI answer.
2. **Given** a name that is defined nowhere, **When** definitions are requested, **Then** the answer is a valid
   empty list, not "not found".

---

### User Story 4 - Clear errors for bad requests and old analyses (Priority: P2)

A client sends a wrong request: an unknown parameter, a parameter twice, an option that does not belong to the
question (`symbol` for `cycles`), a non-integer limit, a limit above the maximum, or asks about a snapshot that
was analyzed with an older graph schema. The API answers with the same error shape as the other `/api/v1`
endpoints and never echoes hostile input back.

**Why this priority**: The API is a public surface of an app that reads untrusted repositories; strict validation
is what `/graph`, `/file` and `/hotspots` already do, and the UI relies on predictable errors.

**Independent Test**: Send each invalid request from a table and check status and error kind; store an analysis
with an older schema version and check the `stale` answer.

**Acceptance Scenarios**:

1. **Given** an unknown or repeated parameter, a missing required parameter, a malformed number or a boolean other
   than `true`/`false`, **When** it is sent, **Then** the answer is 400 `bad_request`.
2. **Given** an option that the question does not take, or a combination the CLI rejects (`level=project` with
   `symbol`, `follow_barrels=true` or `include_type_only=false`), **When** it is sent, **Then** the answer is 400.
3. **Given** a repository or snapshot that is not stored, **When** any question is asked, **Then** the answer is
   404 `not_found` naming which one is missing.
4. **Given** a stored analysis with an older graph schema, **When** any question is asked, **Then** the answer is
   409 `stale` with the advice to analyze it again, as for hotspots.

---

### Edge Cases

- A target given as `./src/app.py`, `src/app.py/` or a node id (`file:src/app.py`, `ext:npm:react`): resolved by the
  same rules as the CLI and MCP.
- A target with `..`, a leading `/` or a backslash: rejected with the "not a repository-relative path" reason, never
  looked up on disk.
- `limit=0`: a valid answer with no items, the total and `truncated` set when there are items.
- A negative limit or one above the maximum: 400.
- `max_depth=0` or negative: rejected as in the CLI.
- `level=project` on a snapshot without C# projects or for a target outside any project: the same answer or error
  as the CLI.
- An `impact` or `cycles` answer on a large snapshot (5,000 files): cut at the limit with total and truncated; the
  full list needs a higher limit up to the maximum.
- Requests for different questions of the same snapshot arriving at once: each is answered independently and
  identically to a lone request.
- A snapshot that is still being analyzed by a job: it is not stored yet, so the answer is 404 until the job is
  done (a partial analysis is never visible, feature 005).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The HTTP API MUST answer each of `dependencies`, `dependents`, `impact`, `neighbors`, `cycles`,
  `key_files`, `definitions`, `overview` and `projects` for a stored snapshot, identified by `repository` and
  `snapshot` like the other `/api/v1` endpoints.
- **FR-002**: Each question MUST have its own read-only `GET` endpoint under `/api/v1`, named after the question,
  in the same style as `/api/v1/hotspots`; `/api/v1/hotspots` stays unchanged.
- **FR-003**: Every answer MUST be computed by the shared graph query layer over the stored graph; the HTTP layer
  only validates parameters, reads the store and returns the answer (constitution VII).
- **FR-004**: The response body MUST be byte-identical to `graphora query <graph> <question> [target] --format
  json` run on the stored graph with the same options and the same effective limit, and equal in content to the
  structured content of the matching MCP tool (except the `repository` field the MCP store mode adds to its
  overview).
- **FR-005**: Parameters MUST match the CLI and MCP options of each question and nothing more:
  `target` (dependencies, dependents, impact, neighbors), `name` (definitions), `include_type_only`
  (all but definitions, overview, projects), `symbol` (dependents), `follow_barrels` (dependents, impact),
  `max_depth` (impact), `level` (dependencies, dependents, impact, cycles) and `limit` (all but overview and
  projects). Booleans are written `true` or `false`.
- **FR-006**: The default `limit` MUST be 50 and the maximum 500, as in the MCP server; for `key_files` the default
  is 10, as for hotspots. Answers MUST report the total and whether they were cut.
- **FR-007**: Unknown, repeated or missing required parameters, malformed values, options the question does not
  take, combinations the CLI rejects and limits outside 0..500 MUST be answered with 400 `bad_request`.
- **FR-008**: A target that cannot be resolved MUST be answered with 404 `not_found` and the reason given by the
  query layer (not in snapshot, skipped and why, `detected_only`, `not_code`, ambiguous package name); a target
  that is not a repository-relative path MUST be answered with 400.
- **FR-009**: A repository or snapshot that is not stored MUST be answered with 404, and a stored analysis with a
  graph schema other than the current one with 409 `stale`, as `/api/v1/hotspots` does.
- **FR-010**: The endpoints MUST answer from the store only: no file system reads, no analysis, no writes, no
  model calls (feature 005 FR-015, FR-018).
- **FR-011**: Error responses MUST use the existing `/api/v1` error shape and MUST NOT echo request values other
  than the names of the repository, snapshot, target or parameter at fault.
- **FR-012**: Answers MUST keep facts and heuristics distinct exactly as the query layer gives them: every link
  carries its confidence and `file:line` citations (constitution IV).
- **FR-013**: The new endpoints MUST be listed in the API's generated description with their parameters, so the
  frontend team can build against it.

### Key Entities

- **Question endpoint**: one graph question over one stored snapshot — its name, the parameters it accepts, their
  defaults and limits.
- **Query answer**: the answer document of the shared query layer (question, target, options, items or groups,
  total, truncated, completeness note), returned unchanged.
- **API error**: the existing `/api/v1` error with a kind (`bad_request`, `not_found`, `stale`, …) and a message.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every fixture repository and every question with its options, the HTTP answer equals the CLI
  JSON answer byte for byte in 100% of cases.
- **SC-002**: Asking the same question twice gives byte-identical answers in 100% of cases.
- **SC-003**: On a stored snapshot at the default ingest limits (5,000 files), each question is answered in under
  3 seconds on a typical developer laptop, including reading the graph from the store.
- **SC-004**: 100% of the invalid requests in the test table get the documented status and error kind, and 0 of
  them echo hostile input back.
- **SC-005**: The four UI needs named in issue #38 (impact mode, cycles list, neighbours and dependents panel,
  symbol search and header numbers) can each be served by one HTTP request without any client-side graph
  computation.
- **SC-006**: All tests that existed before this feature pass unchanged.

## Assumptions

- One endpoint per question (`/api/v1/impact`, `/api/v1/cycles`, …) rather than one generic query endpoint: each
  endpoint validates exactly its own parameters, appears in the generated API description with them, and matches
  the existing `/api/v1/hotspots`, which therefore stays as it is.
- The parameter for `definitions` is `name`, as in the MCP tool; the CLI's positional target becomes `target` for
  the other questions.
- Names in the URL use the query layer's spelling with an underscore (`key_files`), as in MCP; the CLI's
  `key-files` spelling is not repeated.
- The overview is returned as the query layer gives it; the repository name that the MCP store mode adds to its
  overview is already known to the HTTP client from the request and is not added.
- Symbol search is exact and case-sensitive, as `definitions` is today; prefix or fuzzy search is out of scope.
- Each request reads and indexes the stored graph; caching between requests is a plan decision, allowed only if
  answers stay identical.
- Out of scope (own issues): components and clustering for large graphs, cross-origin access (the Vite dev server
  proxies `/api`), PR impact and security screens, authentication.
- Independent of 015 (HTTP bridge): if it lands first, its edges are answered like any other heuristic edges.
