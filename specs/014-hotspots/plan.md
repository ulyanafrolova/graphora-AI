# Implementation Plan: Hotspots

**Branch**: `014-hotspots` | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/014-hotspots/spec.md`

## Summary

This slice adds git history to every analysis and a hotspots query on top of it. Hotspot risk = commits in the
12 months before the snapshot commit × transitive dependents. Bus factor = distinct authors.

What it adds:

- **History reader** (`graphora/history/`, new):
  - **Local folders**: reads `.git` with dulwich as data (R2).
  - **Counting**: walks commits newest first in a fixed order inside the window; counts non-merge commits per
    file path and distinct author e-mails (R3, R4).
  - **GitHub**: fetches only commits and trees of the window over git's read-only HTTPS protocol (blob:none,
    deepen-since, R5).
  - **Partial history**: when time runs out, stops and marks the history `partial` (R7).
- **Graph schema v8**:
  - a required `history` section in `graph.json`;
  - `"history-reader": "1.0.0"` in `extractors` (R6, contracts/graph-schema-v8.md);
  - the store saves it byte for byte, and replaces a stored analysis whose history was retryable when a final
    one arrives (R6).
- **Query layer**: `queries.hotspots`, which joins `key_files` counts with the history and ranks by score (R8).
- **Interfaces** (R9, contracts/interfaces.md):
  - `graphora analyze --no-history`;
  - `graphora query … hotspots`;
  - MCP tool `hotspots` and a history line in `graph_overview`;
  - `GET /api/v1/hotspots`;
  - a `history` flag on HTTP jobs.
- **Verifier**: `question: "hotspots"` claims with `rank`, `count` or `metric` + `value`; reason
  `history_unavailable` (R10, contracts/verifier.md).

What it does not change:
- the import analysis itself;
- 002 tarball and ZIP ingest;
- the store tables;
- the 012 agent tools.

## Technical Context

**Language/Version**: Python ≥ 3.12 (unchanged)

**Primary Dependencies**: none new. dulwich 1.2.19 (already pinned) for reading git and for the smart-HTTP
fetch (`Urllib3HttpGitClient`, `filter_spec`, `shallow_since`); urllib3 comes with it. NetworkX through
`key_files`.

**Storage**: none new. History lives in the graph document, and the 005 store keeps the bytes. The reuse rule
reads the stored graph's history status, so the store schema is unchanged (R6).

**Testing**: pytest.
- Git repositories built at test time with dulwich and hand-written expected counts.
- A local dulwich smart-HTTP server for the fetch.
- Golden fixtures get a hand-written `history` section.
- Store and HTTP tests are marked `db`; one performance test is marked `slow` (R11).

**Target Platform**: backend library, CLI, `graphora serve`, MCP; CI offline with PostgreSQL

**Project Type**: library modules plus CLI, HTTP and MCP surfaces in the existing backend

**Performance Goals**:
- SC-003: 10,000 commits, 5,000 files, ≤ 30 s of history reading;
- SC-003a: GitHub history fetch ≤ 60 s for up to 5,000 commits in the window, no file contents downloaded.

**Constraints**:
- no git binary and no code from the repository;
- history reading stays inside the analyzed folder's `.git` or the temp folder;
- `max_archive_bytes` caps the fetched pack;
- the `max_seconds` deadline is shared with the analysis;
- deterministic output except for `partial`;
- only counts leave the reader, no names or e-mails.

**Scale/Scope**: one snapshot per analysis; up to the existing 5,000-file limit; history window of one year

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Never execute analyzed code | Pass | `.git` is read with dulwich as data, with the snapshot id's safety rules (no alternates, no worktrees). No git binary, hooks or config are run. The GitHub fetch uses only the read-only `upload-pack` service and writes into a temp folder outside the snapshot (R2, R5) |
| II. Deterministic output | **Exception** | Sorted files, fixed walk order, dates from commit data only, canonical JSON. A history cut by the time limit (`partial`) can differ between machines: see Complexity Tracking (R7) |
| III. Provenance on every edge | Pass | Edges are unchanged. History numbers are pinned to `history.commit` (= the snapshot SHA) and its window, and `history-reader@1.0.0` sits in `extractors` |
| IV. Honest confidence | Pass | Missing history is `not_available` with a reason and never zero counts. Partial and shallow cuts are stated. Verifier claims on partial history are `heuristic` (R7, R10) |
| V. Facts by code, words by LLM | Pass | Hotspots and bus factor are computed by `history/` and `queries.hotspots`; the verifier checks hotspot claims in plain code |
| VI. Analyzed content is data | Pass | Commit messages are never read or returned. Author identities are counted in memory only. The MCP description is fixed text |
| VII. One graph query layer | Pass | `hotspots` lives in `graph/queries.py`; CLI, MCP, HTTP and the verifier call it |
| VIII. Golden tests | Pass | Hand-written expected counts for built-in-test git histories. Fixtures' `expected.json` get `history` by hand. A repeat-run test compares bytes |

Post-design re-check (after data-model.md and contracts/): unchanged. One justified exception (II), see below.

## Project Structure

### Documentation (this feature)

```text
specs/014-hotspots/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── graph-schema-v8.md
│   ├── interfaces.md
│   └── verifier.md
├── checklists/requirements.md
└── tasks.md                     # /speckit-tasks
```

### Source Code (repository root)

```text
schema/graph.schema.json                  # v8: history section
fixtures/repos/*/expected.json            # + history (not_available, no_git), by hand
backend/
├── src/graphora/
│   ├── history/                          # new (Anna)
│   │   ├── __init__.py                   # collect_history(...), HISTORY_READER_VERSION
│   │   ├── reader.py                     # walk, window, change sets, authors, partial (R3, R4, R7)
│   │   ├── local.py                      # git source for a local folder (R2)
│   │   └── github.py                     # blobless, deepen-since fetch into a temp bare repo (R5)
│   ├── graph/
│   │   ├── model.py                      # History, FileHistory, GraphDocument.history
│   │   ├── serialize.py                  # SCHEMA_VERSION = 8, history section
│   │   ├── load.py                       # read and check history
│   │   ├── build.py                      # current_extractors() + history-reader
│   │   ├── results.py                    # Item commits/authors/score, Answer.history, text lines
│   │   └── queries.py                    # hotspots(); overview history status
│   ├── ingest/fetch.py                   # FetchedSnapshot: source kind for history
│   ├── pipeline/run.py                   # history step after analysis; reuse rule
│   ├── pipeline/jobs.py                  # history flag in jobs and dedup key
│   ├── store/store.py                    # put: replace retryable history with final (R6)
│   ├── cli/__init__.py                   # analyze --no-history, query hotspots, info line
│   ├── api/routes.py                     # GET /api/v1/hotspots
│   ├── api/jobs.py                       # history body key / query parameter
│   ├── mcp/server.py                     # hotspots tool, overview line
│   └── verify/claims.py, graph_checks.py # hotspots claims, metric/value, history_unavailable
└── tests/
    ├── history_repos.py                  # builds test git repositories with dulwich
    ├── unit/test_history_reader.py       # window, merges, renames, deletes, root, shallow, authors, partial
    ├── unit/test_history_model.py        # History rules, serialize/load round trip
    ├── unit/test_hotspots_query.py       # score, order, limit, not available, include_type_only
    ├── unit/test_verify_hotspots.py      # claims and reasons
    ├── integration/test_history_github.py    # local smart-HTTP server: fetch, too_large, time_limit, redirect, errors
    ├── integration/test_history_cli.py       # analyze (local, dirty, --no-history), query hotspots, repeat bytes
    ├── integration/test_hotspots_api.py      # db: endpoint, jobs flag, store reuse rule
    ├── integration/test_history_performance.py  # slow: SC-003
    └── golden/test_fixtures.py           # + history section
```

**Structure Decision**:
- `history/` is new and owned by Anna (the "history (hotspots)" line in `docs/product/team-workflow.md`).
- The query stays in `graph/` (constitution VII).
- Changes to Ulyana's modules (`graph/model.py`, `serialize.py`, `load.py`, `build.py`, `store/`, `api/`,
  `pipeline/`) are kept small and listed in Coordination.

## Coordination

- **Schema v8** touches shared files. Ulyana reviews `graph/model.py`, `serialize.py`, `load.py`, `build.py`
  (one line in `current_extractors`) and `schema/graph.schema.json` in PR #35.
- **Store reuse rule** (`store/store.py`, Ulyana's): one condition in `put` and in the pipeline's reuse check
  (R6).
- **HTTP**: `/api/v1/hotspots` and the job `history` flag change Ulyana's `api/` and `pipeline/`. Feature 015 (HTTP
  bridge) may fold the endpoint into a general query route later.
- **Verifier claims**: the new `metric`/`value` fields are optional, so 012 agents are unaffected. 012/013 may use
  them to explain hotspots.
- **Docs**: CLAUDE.md gets the `--no-history` and `query … hotspots` command lines. `docs/demo/README.md` § 9
  already describes the feature.

## Commits

- A commit after every plan and tasks phase, and more than one per phase where a phase has separable parts (for
  example model + schema, then reader, then GitHub fetch).
- Small lowercase English messages.
- This plan is committed as `plan: 014 hotspots`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Constitution II: a history cut by the time limit (`partial`) can differ between machines | The user chose (spec clarification, option B) to show the newest part of a very long history instead of nothing. Without it, very large repositories never get hotspots under the default 300 s limit | (a) Always `not_available` on the time limit: deterministic, but huge local repositories get no hotspots at all. (b) A fixed commit cap: deterministic, but rejected in clarification and arbitrary across repository sizes. **Containment**: commits are read newest first in a fixed order, so a partial history is always a prefix of the same sequence. It is marked `partial` with the number of commits read and the oldest date, verifier claims on it are only `heuristic`, it is retryable in the store, and every non-partial result stays byte-identical (SC-002) |
