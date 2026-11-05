# Implementation Plan: Analysis Storage and HTTP API

**Branch**: `spec/005-storage-http-api` | **Date**: 2026-11-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-storage-http-api/spec.md`

## Summary

Keep each analysis in PostgreSQL under (repository, snapshot id): the exact graph bytes, schema and extractor
versions, warnings, and the exact bytes of every coverage file that has text, deduplicated by hash. The CLI
gets `analyze --store` (reuse a stored analysis when versions match; for GitHub, skip the download) and
`serve`, which runs a read-only FastAPI app with three endpoints: list repositories, get a graph, get a file
or line range. To store exactly what was analyzed, `graph.build` exposes the bytes it already reads. The graph
schema does not change.

## Technical Context

**Language/Version**: Python 3.12 (`requires-python >=3.12`)

**Primary Dependencies**: existing (tree-sitter, dulwich); new runtime: `psycopg[binary]` 3, `fastapi`,
`uvicorn`; `jsonschema` moves from dev to runtime (R8). New dev: `httpx` (for `TestClient`). Exact versions
pinned in `pyproject.toml` and `uv.lock`, as for tree-sitter.

**Storage**: PostgreSQL 17, three tables plus `store_meta` ([data-model.md](data-model.md))

**Testing**: pytest; new marker `db` for tests that need `GRAPHORA_TEST_DATABASE_URL`; FastAPI `TestClient`
in-process; existing offline guard stays on (R1, R12)

**Target Platform**: developer laptop (macOS, Linux) and GitHub Actions `ubuntu-latest` with a `postgres:17`
service

**Project Type**: CLI + local web service (backend only in this slice)

**Performance Goals**: SC-002 reuse < 2 s; SC-004 graph of a 5,000-file snapshot < 2 s, file or line range
< 0.5 s

**Constraints**: byte-identical graph bytes (FR-013); deterministic bodies (FR-016); read-only API; no file
system reads in the API; binds to `127.0.0.1` by default; suite still offline

**Scale/Scope**: up to the existing limits per analysis (5,000 files, 50 MB); tens of analyses per store

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | Status | How |
|---|---|---|
| I. Never execute analyzed code | Pass | Store and API only read bytes already produced; API has no write or analyze operation (FR-018); ingest limits unchanged |
| II. Deterministic output | Pass | Graph served as stored bytes; other bodies sorted keys and sorted lists; no timestamps in tables or bodies (R3, R11) |
| III. Provenance on every edge | Pass | Graph unchanged; stored file bytes are the analyzed bytes (R4) and lines split like the adapters (R5), so `file:line@snapshot` can be checked against stored text |
| IV. Honest confidence | Pass | Not touched; graph served as is |
| V. Facts by code | Pass | No model involved |
| VI. Analyzed content is data | Pass | File text is returned as JSON data only; nothing interprets it |
| VII. One graph query layer | Pass | No graph queries in `store/` or `api/` (FR-019); schema unchanged |
| VIII. Golden tests | Pass | Round-trip tests over every fixture compare stored/served bytes with plain CLI output, run twice |
| Tech constraints | Pass | PostgreSQL keyed by (repository, snapshot), FastAPI, `uv` |
| Workflow | Pass | One slice; change to `ingest/fetch.py` (Anna's module) is one optional parameter and the PR requests her review |

Post-design re-check: still passes; no deviations, Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/005-storage-http-api/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md          # analyze --store, serve, exit status 6
│   ├── http-api.md     # three GET endpoints, error shape
│   └── store-api.md    # Python store API for 006/007/008
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
docker-compose.yml                 # NEW: postgres:17 on 127.0.0.1:5432 (dev)
Makefile                           # + db, db-down
.github/workflows/checks.yml       # + postgres service, GRAPHORA_TEST_DATABASE_URL

backend/
├── pyproject.toml                 # deps, `db` marker
├── src/graphora/
│   ├── graph/build.py             # analyze(), current_extractors(); build() becomes a wrapper (R4, R6)
│   ├── ingest/fetch.py            # fetch_snapshot(..., sha=None) (R6)
│   ├── store/                     # NEW
│   │   ├── __init__.py            # Store, StoreUnavailable, StoreResult, StoredAnalysis, FileText
│   │   ├── schema.sql             # tables, store_meta
│   │   ├── store.py               # open, put, find_reusable, list, get_analysis, get_file
│   │   └── text.py                # has_text rule, line splitting (R5)
│   ├── api/                       # NEW
│   │   ├── __init__.py            # create_app(store)
│   │   ├── routes.py              # /api/v1/repositories, /graph, /file
│   │   └── errors.py              # error kinds and handlers (R11)
│   └── cli/__init__.py            # --store, --database, serve, exit 6
└── tests/
    ├── conftest.py                # store fixture (db marker, truncate per test)
    ├── unit/test_store_text.py    # line splitting, decoding, BOM, empty file
    ├── unit/test_build_analyze.py # analyze() == build(); contents are the read bytes
    ├── integration/test_store.py  # put/reuse/replace, atomicity, concurrency, restart (new connection)
    ├── integration/test_store_cli.py   # --store, GitHub reuse via fake_github, exit 6, no-db unchanged
    ├── integration/test_api.py    # endpoints, errors, hostile paths, determinism
    └── golden/test_store_roundtrip.py  # every fixture: stored == served == CLI bytes, twice
```

**Structure Decision**: Backend-only slice in the existing `backend/` package. New `store/` and `api/`
folders as listed in `CLAUDE.md`. The analyze-and-store flow lives in the CLI for now; 007 moves it behind
HTTP and reuses `Store.put`.

## Complexity Tracking

No constitution violations.
