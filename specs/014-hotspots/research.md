# Research: Hotspots

Decisions behind `plan.md`. Each item: decision, rationale, alternatives considered.

## R1. Where the code lives

**Decision**: A new package `backend/src/graphora/history/` (owned by Anna) reads git history and builds the
history summary. The hotspots query is `queries.hotspots` in `graph/queries.py`. The graph document gets a
`history` section (`graph/model.py`, `serialize.py`, `load.py`, `schema/graph.schema.json`). The CLI, the
pipeline, MCP, the HTTP API and the verifier only call these.

**Rationale**: Reading git is ingest work, not a graph query. The ranking joins history with `key_files`, so it
is a graph query and belongs in `graph/` (constitution VII). `history/` sits next to `ingest/` and depends on
nothing in `graph/` except the model types.

**Alternatives considered**: Collecting history inside `graph/build.py`. Rejected: `build.py` is Ulyana's and
analyzes a folder. History needs to know the source (GitHub, ZIP), and for GitHub it is fetched separately.

## R2. Reading local history without running git

**Decision**: Use `dulwich.repo.Repo` on the analyzed folder, under the same rule as the snapshot id. History is
read only when:

- the snapshot id is a commit SHA or `<sha>+dirty:<hash>`;
- `_usable_git_dir(root)` holds (a real `.git` directory, no `objects/info/alternates`, no `commondir`).

The snapshot commit is the SHA part of the snapshot id, not a fresh read of `HEAD`, so history and graph always
refer to the same commit. Any dulwich error (missing object, corrupt pack) makes the history
`not_available: unreadable`.

**Rationale**: The 002 snapshot-id code already uses dulwich and the same safety checks (constitution I: data
only, no git binary, no hooks, no config execution). Using the SHA from the snapshot id avoids a race with a
`HEAD` that moved during the analysis.

**Alternatives considered**: Running `git log --name-only`. Rejected: running a binary on an untrusted repository
can trigger its config (`core.fsmonitor`, hooks), and the team rule is "no git binary". pygit2/libgit2 was
rejected as a new native dependency for no gain.

## R3. Which commits count and how a change set is computed

**Decision**:

- **Walk**: start at the snapshot commit and follow parents. The order is fixed: a heap keyed by
  `(-commit_time, sha)`, newest first, ties broken by SHA.
- **Window**: a commit is in the window if its commit time is not earlier than the snapshot commit's time minus
  365 × 86,400 s. The walk does not continue past a commit outside the window.
- **Merges**: a commit with two or more parents is a merge. It is not counted, but its parents are walked.
- **Change set**: for a commit with one parent, `dulwich.diff_tree.tree_changes(store, parent.tree,
  commit.tree)` with no rename detection. The changed paths are new paths of `add` and `modify` changes; `delete`
  is ignored. A type change (file ↔ symlink) counts as `modify`. Without rename detection a rename reads as delete
  plus add, so the new path counts as added (spec edge case: renames are not followed).
- **Root commit** (no parents in the commit object): compared with the empty tree, so every file counts as added.
- **Shallow commit**: a commit listed in the repository's shallow set (`Repo.get_shallow()`) whose parents are
  missing. Its change set is unknown, so it is not counted. `shallow_skipped` is increased and the summary is
  marked cut by shallow history.
- **Which paths are kept**: only paths of file nodes of the document (analyzed Python, TS/JS and C# files). Other
  paths cannot have dependents and would only make `graph.json` bigger.
- **Authors**: `commit.author`, normalized to the lower-case e-mail between `<` and `>`. If there are no angle
  brackets, the whole author string in lower case is used. Only counts leave the module (FR-015).

**Rationale**: `tree_changes` compares tree entries by object id. It never reads file contents, so it also works
on a blobless GitHub fetch (R5). Its C extension (`_diff_tree`) keeps 10,000 commits well under the 30 s target
(SC-003). The fixed order makes a time-cut history always the newest part of the window (R7). The window and
merge rules follow the spec clarifications.

**Alternatives considered**:
- First-parent only. Rejected: commits on merged branches would be lost.
- Diff a merge against its first parent. Rejected: that counts every change of a merged branch a second time.
- `dulwich.walk.Walker`. Rejected: it does not give a documented tie-break and window cut in one pass.
- Applying `.mailmap`. Rejected: not in the spec, and it is one more file from the repository to trust; it can
  come later.

## R4. Time handling and dates

**Decision**: The window is measured from `commit_time` of the snapshot commit (the committer date, UTC seconds).
Dates in the summary (`window_start`, `newest`, `oldest`) are written as `YYYY-MM-DDTHH:MM:SSZ` in UTC and are
computed only from commit data. Commit times earlier than the window start stop the walk on that branch. Commits
dated after the snapshot commit (clock skew) are still counted, because they are reachable and in the window by
the rule.

**Rationale**: Constitution II and FR-009: no wall-clock time. The committer date is also what git's
`deepen-since` uses (R5), so the local and GitHub cuts agree.

**Alternatives considered**: Author date. Rejected: rebases keep old author dates, and the GitHub cut works on
committer dates.

## R5. GitHub history: what is fetched and how

**Decision**: After the tarball is analyzed, `history/github.py` fetches over git smart HTTP from
`https://github.com/<owner>/<repo>.git`, with dulwich's `Urllib3HttpGitClient.fetch_pack`. It always asks for the
snapshot SHA itself (a `want` by SHA, not by ref). The fetch has two steps:

1. `depth=1`, `filter_spec=b"blob:none"`: only the snapshot commit and its tree. This gives the commit time.
2. `shallow_since=<window start − 30 days>`, `filter_spec=b"blob:none"`: commits and trees of the window plus a
   30-day margin.

**Why the 30-day margin**: git's `deepen-since` marks a commit as shallow when its parents are older than the
date. With the exact window start as the date, the oldest commits inside the window would be shallow, so their
change sets would be unknown. With the margin those boundary commits lie outside the window.

**Where the data goes**:
- `pack_data` writes into `object_store.add_pack()` of a bare repository in `<temp>/history.git`. It is a sibling
  of the extracted snapshot folder, never inside it, and is removed with the temp folder.
- The `new_shallow` SHAs of each fetch go to the repository's shallow set, which R3 reads.
- Then the same reader as for local folders (R3) runs on the bare repository.

**Network rules**:
- Same User-Agent as 002.
- No credentials.
- Redirects are refused (urllib3 `Retry(redirect=0)`): a redirect means `not_available: fetch_failed`.
- Each request's timeout is `deadline.remaining()`.

**Limits**: The pack bytes are counted in `pack_data`. Over `max_archive_bytes` the fetch stops:
`not_available: too_large`. When the deadline runs out during the fetch: `not_available: time_limit`. Any other
HTTP, protocol or pack error: `not_available: fetch_failed`. None of these fail the analysis (spec US2 scenario
4).

**Rationale**:
- The read-only `upload-pack` service is the only anonymous way to get the commit graph without one request per
  commit.
- GitHub supports protocol v2 with `filter` and `deepen-since`, so the download is about the size of the window's
  trees.
- dulwich 1.2.19, already pinned, supports `filter_spec` and `shallow_since` (checked in
  `dulwich/client.py`).
- The window rules are applied by our reader, not by the server. If a server ignores the filter or `deepen-since`
  (as dulwich's own test server does for `deepen-since`), the download is only bigger, never wrong.

**Alternatives considered**:
- GitHub REST `GET /commits/{sha}` per commit. Rejected: 60 requests an hour without a token (spec
  clarification).
- GitHub GraphQL. Rejected: needs a token.
- One fetch with a date computed from the API's commit JSON. Rejected: when the store check already gave the SHA
  there is no API call to reuse, and step 1 costs a few kilobytes.
- Replacing the tarball with a full clone. Rejected: it changes 002 ingest and downloads all blobs.

**Order**: History is fetched after the analysis, so a slow fetch can never starve the analysis of time. Only the
time left of the same `max_seconds` deadline is used.

## R6. Where the history goes and how reuse works

**Decision**:
- **Graph document**: a required top-level `history` object; the schema version goes from 7 to 8
  (contracts/graph-schema-v8.md). `extractors` gains `"history-reader": "1.0.0"`. A change to the counting rules
  bumps that version, and the 005 store then replaces old analyses as it does for adapters.
- **Library default**: `GraphDocument.history` defaults to `not_available` with reason `not_collected`, so code
  that builds a document without the flow (tests, `build()` callers) stays valid. The CLI and the pipeline always
  set it.
- **Final and retryable histories**:
  - *final*: `available`, or `not_available` because of the source (`no_git`, `zip`, `unreadable`);
  - *retryable*: `partial`, or `not_available` with `skipped`, `fetch_failed`, `too_large`, `time_limit` or
    `not_collected`.
- **Store `put`**: an existing analysis is reused as today, except when the stored history is retryable and the
  new one is final. Then the stored analysis is replaced.
- **Pipeline reuse** (`find_reusable` before fetching): a stored analysis is reused only if history is not wanted
  or the stored history is final.

**Rationale**:
- The spec clarification puts the summary in `graph.json`. The store saves the bytes unchanged, so `graphora
  query`, MCP and HTTP read the same data.
- Without the final/retryable rule:
  - one `--no-history` run, or one network error, would stick to a snapshot forever;
  - a reused old analysis would answer "no history" even though it can be computed.

**Alternatives considered**:
- A separate store table. Rejected in the spec clarification (graph files would have no hotspots).
- A new store column for the history status. Rejected: the status is read from the stored graph bytes, and a store
  version bump is not needed.

## R7. Time limit: partial history

**Decision**:
- **Reading stops**: the reader (R3) checks `deadline.remaining()` before each commit. When the time is up it
  stops and returns status `partial` with what it has. Because the walk is newest first in a fixed order, a
  partial history is always the newest part of the window, cut at a commit boundary.
- **What is reported**: `commits_read` and the `oldest` date reached.
- **No commits read**: the status is `not_available: time_limit`.
- **No error**: the reader never raises `LimitExceeded`, so the analysis still finishes and is written or stored.

**Rationale**: Spec clarification (option B). This is the one exception to constitution II and is recorded in the
plan's Complexity Tracking. The size limit and the GitHub fetch stay all-or-nothing, because an interrupted pack
cannot be read (R5).

**Alternatives considered**:
- A separate history time budget. Rejected: it would be a new limit in the CLI and the HTTP API for one case.
- A fixed commit cap, which would be deterministic. Rejected in clarification in favour of the time limit, and it
  would cut small slow repositories and large fast ones arbitrarily.

## R8. The hotspots query

**Decision**: `queries.hotspots(ix, *, include_type_only=True, limit=10) -> Answer` works in four steps:

1. Run `key_files(ix, include_type_only=..., limit=None)`, which gives transitive and direct dependents per file.
2. Join with `ix.doc.history.files` by path.
3. Compute `score = commits × transitive_dependents` and keep files with score > 0.
4. Sort by `(-score, -commits, -transitive_dependents, path)`, then apply the limit with the usual `_answer`
   (total, truncated).

The `Answer` carries `history`: the summary without the per-file list. When the status is `not_available` the
items are empty, `total` is 0, and the answer still has `history` with the reason. It is not an error (spec US2
scenario 1).

**Rationale**: It reuses the tested `key_files` count, so FR-005 holds by construction. Answers keep the 004 shape,
so CLI, MCP and HTTP render them like other questions.

**Alternatives considered**: Computing scores at analysis time and storing them in `graph.json`. Rejected: the
score depends on the `include_type_only` option, and the graph stays the source of truth.

## R9. Interfaces

**Decision** (details in contracts/interfaces.md):

| Interface | Change |
|---|---|
| CLI `analyze` | `--no-history` |
| CLI `query` | question `hotspots` with `--limit` (default 10), `--no-type-only`, `--format` |
| MCP | tool `hotspots(include_type_only=True, limit=10)`; `graph_overview` also shows the history status |
| HTTP | `GET /api/v1/hotspots?repository&snapshot[&limit][&include_type_only]` |
| HTTP jobs | GitHub body key `history` (boolean, default true); ZIP query parameter `history`. A ZIP has no history anyway; the parameter is accepted for symmetry |
| Job deduplication | the key includes the history flag |

**Rationale**: FR-012 and FR-017. The HTTP endpoint follows the existing `/api/v1` style (query parameters, store
only).

**Alternatives considered**: A generic `/api/v1/query` endpoint. Rejected: that is feature 015's (Ulyana's)
design; a single endpoint now is easy to fold into it.

## R10. Verifier

**Decision** (contracts/verifier.md): Query claims accept `question: "hotspots"` (no target, option
`include_type_only`). A claim names a member with either `rank` or `metric` + `value`, or gives a `count`.

- **New `Claim` fields**: `metric` (`commits`, `authors`, `score`, `transitive_dependents`,
  `direct_dependents`) and `value`.
- **New reason**: `history_unavailable`.
- **Wrong value**: rejected with `count_mismatch` and the hint `actual N`. A wrong rank is rejected with
  `rank_mismatch`, as for `key_files`.
- **Status when the claim holds**:
  - `verified` when the history is `available`;
  - `heuristic` when the history is `partial` (the number depends on how much was read) or when the member's
    dependents include a heuristic link (same rule as `key_files` rank).

**Rationale**: FR-013 and US3. The new fields are optional, so 012's existing claims are unchanged. Ulyana reviews
the shape in the PR (round 5 coordination).

**Alternatives considered**: Separate claim kinds per number. Rejected: one `metric` field covers all of them and
keeps `Claim` small.

## R11. Testing approach

**Decision**:
- **Test repositories**: built at test time with dulwich (`tests/history_repos.py`). Commits, authors, dates,
  merges, renames and deletions are given in code. Fixtures cannot hold a nested `.git` (spec assumption).
- **Expected values**: written by hand in the tests, never generated.
- **GitHub fetch tests**:
  - dulwich's WSGI server (`dulwich.web.make_wsgi_chain`) serves such a repository on `127.0.0.1` in a thread;
    a test hook replaces the base URL, like `ingest.github._open` in 002;
  - limits are tested with tiny `max_archive_bytes` and an expired deadline;
  - redirects are refused;
  - a server error gives `fetch_failed`.
- **Golden fixtures**: they are not git roots, so every fixture gets `history: not_available, no_git`. A
  `history` section is added to the projected sections of `test_fixtures.py`, and the fixtures' `expected.json`
  get it by hand.
- **Database and speed**: store and HTTP tests are marked `db`. One performance test (10,000 commits, 5,000
  files) is marked `slow`.

**Rationale**: Golden tests stay hand-written ground truth (constitution VIII), and nothing in CI needs network
access.

**Alternatives considered**: Recorded real GitHub responses. Rejected: binary packs are opaque to review, and
GitHub specifics (v2, `deepen-since`) are covered by the "never wrong, only bigger" rule in R5 plus a manual
check in quickstart.md.
