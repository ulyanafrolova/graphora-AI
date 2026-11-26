# Implementation Plan: Graph Queries over HTTP

**Branch**: `018-http-queries` | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/018-http-queries/spec.md`

## Summary

The web UI (rounds 6–7) needs the graph questions that only the CLI and MCP answer today. This slice adds nine
read-only `GET` routes under `/api/v1`: `dependencies`, `dependents`, `impact`, `neighbors`, `cycles`,
`key_files`, `definitions`, `overview`, `projects`. Each one calls the existing `graph/queries.py` function over
a stored snapshot and returns `results.dumps(answer)`, the same bytes as `graphora query … --format json`.

What it adds:
- **`api/questions.py`** (new): one table of questions (query function, target parameter, options, default limit)
  and a loop that registers one route per row, with parameter checks and OpenAPI parameters (R1, R2, R3, R7).
- **`api/routes.py`**: a shared `stored_index` helper (404 missing, 409 stale, load + index) used by `/hotspots` and
  the new routes (R4).
- **`api/__init__.py`**: includes the new router.
- **Errors**: `NodeNotFound` → 404 (400 for `invalid_path`), `ValueError` → 400 (R5).

What it does not change: the query layer, the graph schema, the store, the CLI, MCP, `/hotspots` behaviour, jobs
and `/ask`. No cache between requests (R6).

## Technical Context

**Language/Version**: Python ≥ 3.12 (unchanged)

**Primary Dependencies**: none new. FastAPI (existing), the `graph.queries` layer.

**Storage**: PostgreSQL store of feature 005, read only; no schema change.

**Testing**: pytest. Golden byte comparison HTTP vs CLI over every fixture's `queries.json`, plus `overview` and
`definitions` (`db`); an error-table integration test (`db`); one performance test (`slow`, `db`) (R8).

**Target Platform**: `graphora serve` (local HTTP service); CI with PostgreSQL

**Project Type**: web service routes in the existing backend

**Performance Goals**: SC-003: each question on a stored 5,000-file snapshot in < 3 s, store read included

**Constraints**: read-only, store only, no model calls; responses byte-identical to the CLI; parameters checked
before the store is read; error messages name only the value at fault.

**Scale/Scope**: nine routes; graphs up to the default 5,000-file ingest limit; answers capped at 500 items.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Never execute analyzed code | Pass | Routes read stored graph bytes only; no file system, no analysis, no tools with side effects |
| II. Deterministic output | Pass | The body is `results.dumps` (sorted keys, fixed layout); no cache, no timestamps; a repeat test compares bytes |
| III. Provenance on every edge | Pass | Answers are returned unchanged, with every link's `file:line`, confidence and extractor |
| IV. Honest confidence | Pass | `resolved`/`heuristic` and the completeness note pass through; not-analyzed targets get their reason, not an empty answer |
| V. Facts by code, words by LLM | Pass | Every answer is computed by `graph/queries.py`; no model is called |
| VI. Analyzed content is data | Pass | No model sees the answers here; error messages never echo hostile input beyond the value at fault |
| VII. One graph query layer | Pass | The routes only validate, read the store and call `graph.queries`; this feature exists so the frontend does not reimplement queries |
| VIII. Golden tests | Pass | HTTP answers are compared byte for byte with the CLI on every fixture query case |

Post-design re-check (after data-model.md and contracts/): unchanged, no exceptions.

## Project Structure

### Documentation (this feature)

```text
specs/018-http-queries/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md                     # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── src/graphora/api/
│   ├── questions.py                         # new: question table, routes, parameter kinds, OpenAPI params
│   ├── routes.py                            # stored_index helper; /hotspots uses it
│   └── __init__.py                          # include questions.router(store)
└── tests/
    ├── golden/test_http_queries.py          # db: every queries.json case + overview/definitions == CLI bytes
    ├── integration/test_http_queries_api.py # db: defaults, error table, OpenAPI, no echo, concurrency
    ├── integration/test_http_queries_performance.py  # slow, db: SC-003
    └── integration/test_api.py              # path list of test_only_read_endpoints
CLAUDE.md                                    # one curl line for the query routes
```

**Structure Decision**: The new routes live in their own module of `api/` so Ulyana's `routes.py` changes only by
the shared helper. No new package; nothing outside `api/`, tests and CLAUDE.md changes.

## Coordination

- `api/` is Ulyana's module: she reviews `questions.py`, the `stored_index` change in `routes.py` and the one line in
  `__init__.py`.
- 015 (HTTP bridge, PR #37) bumps the schema; whichever merges second keeps the `stale` rule working through
  `SCHEMA_VERSION` without changes here.
- Frontend (rounds 6–7) builds against `contracts/http-api.md` and `/api/v1/docs`.

## Commits

- One commit per task of tasks.md where possible, pushed at the end of each phase.
- Small lowercase English messages. This plan is committed as `plan: 018 http queries`.

## Complexity Tracking

No constitution violations.
