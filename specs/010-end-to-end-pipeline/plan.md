# Implementation Plan: End-to-End Pipeline (Import and Analyze over HTTP)

**Branch**: `010-end-to-end-pipeline` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-end-to-end-pipeline/spec.md`

## Summary

Move the analyze-and-store flow of `graphora analyze --store` into one shared function,
`graphora.pipeline.run_pipeline`, that reports its stage through a callback. The CLI keeps calling it with
unchanged output. `graphora serve` gets a `JobRunner`: a bounded FIFO queue and worker threads (default 1)
that run the same function in the background. Each job uses its own store connection and its own sub-folder
of a locked work folder. Three endpoints are added: start a job from a GitHub link (JSON), start a job from a
streamed ZIP body, and read a job's status. The status is a deterministic JSON body, and a `done` job names
the stored repository and snapshot that the 005 read API and the 006 MCP server already serve. No new
dependency, no schema change, no new tables.

## Technical Context

**Language/Version**: Python 3.12 (`requires-python >=3.12`)

**Primary Dependencies**: existing only: FastAPI, uvicorn, psycopg 3, tree-sitter, dulwich. No
`python-multipart` (R4) and no task queue (R1).

**Storage**: PostgreSQL through the 005 `Store`, unchanged. Jobs live in memory (data-model.md).

**Testing**: pytest, FastAPI `TestClient` in-process, `fake_github` and `tests/archives.py` reused; `db`
marker for store tests; unit tests of `JobRunner` with an injected stub pipeline (R12)

**Target Platform**: developer laptop (macOS, Linux) and GitHub Actions `ubuntu-latest` with `postgres:17`

**Project Type**: CLI + local web service (backend only)

**Performance Goals**: SC-002 start answer < 1 s; SC-003 reuse < 2 s with zero downloads

**Constraints**: stored graph byte-identical to `analyze --store` (FR-013); deterministic status bodies
(FR-009); no analyzed code executed; limits on every job; upload stopped at the size limit; no leftover files;
binds to `127.0.0.1` by default; suite offline

**Scale/Scope**: one user; 1 running and up to 20 waiting jobs by default; per job the existing limits
(5,000 files, 50 MB, 300 s, 200 MB archive)

## Constitution Check

*GATE: checked before Phase 0 and again after Phase 1.*

| Principle | Status | How |
|---|---|---|
| I. Never execute analyzed code | Pass | Jobs run the existing static pipeline only; limits enforced on every job and on the upload stream (FR-015, FR-017); archive extraction unchanged; no local paths accepted over HTTP (FR-003). Agent and MCP tools stay read-only; only the HTTP API gains "start an analysis" (FR-023) |
| II. Deterministic output | Pass | Graph produced by the same function as the CLI (R2); status bodies sorted, no timestamps or queue positions (R6) |
| III. Provenance on every edge | Pass | Graph unchanged |
| IV. Honest confidence | Pass | Not touched; status counts `unresolved` edges as the CLI does |
| V. Facts by code | Pass | No model involved |
| VI. Analyzed content is data | Pass | Nothing reads file contents beyond the existing analysis; messages never echo file contents |
| VII. One graph query layer | Pass | No graph queries in `pipeline/` or the new routes; schema unchanged |
| VIII. Golden tests | Pass | Every fixture through HTTP (GitHub fake and ZIP) compared byte for byte with `analyze --store`, three runs (SC-001) |
| Tech constraints | Pass | FastAPI, PostgreSQL keyed by (repository, snapshot), `uv`; no new dependency |
| Workflow | Pass | One slice, one branch, one PR. `ingest/fetch.py` (Anna's module) gets one optional parameter (R8); the PR requests her review |

Post-design re-check: still passes. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/010-end-to-end-pipeline/
├── spec.md
├── plan.md
├── research.md            # R1–R12
├── data-model.md          # Job, stages, JobRunner
├── quickstart.md
├── contracts/
│   ├── http-api.md        # POST /jobs, POST /jobs/zip, GET /jobs/{id}
│   ├── cli.md             # serve options
│   └── pipeline-api.md    # run_pipeline, JobRunner, fetch_snapshot(workdir)
├── checklists/requirements.md
└── tasks.md               # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── src/graphora/
│   ├── pipeline/                  # NEW (Ulyana: "the end-to-end pipeline")
│   │   ├── __init__.py            # run_pipeline, PipelineLimits, PipelineResult, Stage
│   │   ├── run.py                 # the shared analyze-and-store flow (R2)
│   │   ├── messages.py            # limit messages for CLI and API (R11)
│   │   └── jobs.py                # JobRunner, Job, JobStatus, QueueFull, JobDeadline (R1, R6–R8, R10)
│   ├── api/
│   │   ├── __init__.py            # create_app(store, runner=None)
│   │   ├── jobs.py                # NEW: the three job endpoints, input checks (R4, R5, R9)
│   │   └── errors.py              # + limit (413), too_many_jobs (429); 405 message
│   ├── ingest/fetch.py            # fetch_snapshot(..., workdir=None) (R8, Anna's review)
│   └── cli/__init__.py            # analyze --store calls run_pipeline; serve options and runner lifecycle
└── tests/
    ├── unit/test_jobs.py                  # queue, workers, dedup, stages, stop, status bytes (stub pipeline)
    ├── unit/test_job_input.py             # link, ref, name, limits checks
    ├── unit/test_fetch_workdir.py         # temp folder created inside workdir and removed
    ├── integration/test_api_jobs.py           # db: US1 over TestClient + fake_github
    ├── integration/test_api_jobs_reuse.py     # db: US2 reuse and dedup
    ├── integration/test_api_jobs_zip.py       # db: US3 uploads
    ├── integration/test_api_jobs_failures.py  # db: US4 failure kinds, FR-023
    ├── integration/test_jobs_cleanup.py   # work-dir lock, leftovers removed at start, no files after jobs
    ├── integration/test_store_cli.py      # existing: still passes unchanged (FR-022)
    └── golden/test_pipeline_equivalence.py  # db: every fixture via GitHub fake and ZIP == analyze --store, ×3
```

Docs touched in the final pass: `CLAUDE.md` (commands), `docs/product/project-context.md` § 5 (actual
endpoints).

**Structure Decision**: Backend-only slice in the existing package. The new `pipeline/` folder holds the flow
that both the CLI and the service run, so neither owns a copy. The API layer only validates input, streams
uploads and serializes status.

## Complexity Tracking

No constitution violations.
