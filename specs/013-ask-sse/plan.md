# Implementation Plan: Ask over HTTP with a Streamed Trace

**Branch**: `013-ask-sse` | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/013-ask-sse/spec.md`

## Summary

`graphora serve` gets `POST /api/v1/ask`: a question about one stored snapshot, answered by the 012 agents and
streamed as server-sent events (R1, R2). Each 012 trace event is sent as a `step` as it happens; the stream ends
with one `answer` (the `graphora ask --json` document) or one `error`.

How:

- **Streaming**: FastAPI's built-in `EventSourceResponse` (0.162) with its 15-second keep-alive; no new
  dependency (R2).
- **Threads**: each ask runs the synchronous agents in its own daemon thread with its own store connection;
  events cross to the event loop through an `asyncio.Queue` (R3, R6).
- **Slots**: an `AskService` allows `--asks` (default 1) runs at once, refuses more with 429 `busy`, and is
  separate from the analysis job workers (R4).
- **Stop**: 012 `ask` gets a `stop` callable checked before each model and tool call, and the end reason
  `stopped`; a disconnect or shutdown sets it (R5).
- **Refusals before the stream**: body, pair, slot and model setting are checked first and answered as normal
  API errors (R1, R4, R6).

What it does not change: graph schema, store schema, 011 verifier and tools, MCP server, the existing endpoints.

## Technical Context

**Language/Version**: Python ≥ 3.12 (unchanged)

**Primary Dependencies**: none new. FastAPI 0.162 (`fastapi.sse`), uvicorn, the 012 agents, the 005 store

**Storage**: reads the 005 store only; no writes

**Testing**: pytest with `TestClient` streams and the 012 `ScriptedModel`; store tests marked `db`; no live
model in CI

**Target Platform**: `graphora serve` on 127.0.0.1 on a developer laptop

**Project Type**: an endpoint and a service object in the existing backend, plus a small 012 extension

**Performance Goals**: first `step` within 1 s (SC-001); refusals within 1 s (SC-003)

**Constraints**: read-only; ≤ `--asks` concurrent runs; stop after at most the running model call; keep-alive
every 15 s

**Scale/Scope**: one laptop, a handful of concurrent viewers, one ask at a time by default

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Never execute analyzed code | Pass | the endpoint runs the read-only 012 agents over the stored snapshot; nothing is written (FR-013) |
| II. Deterministic output | Pass | stream content equals the 012 trace and `Run` (deterministic for fixed model replies); JSON with sorted keys; no timestamps added |
| III. Provenance on every edge | Pass | the answer carries 012 citations unchanged |
| IV. Honest confidence | Pass | facts, likely and hypotheses delivered as 012 builds them; the UI gets the same parts |
| V. Facts by code, words by LLM | Pass | no new reasoning; Reviewer and verifier unchanged; budget unchanged |
| VI. Analyzed content is data | Pass | `step` messages carry no file content or model text (FR-006) |
| VII. One graph query layer | Pass | no queries here; agents use 011 tools |
| VIII. Golden tests | Pass | stream tests on stored fixtures, asserting structure and equality with the CLI output |

Post-design re-check: still passes. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/013-ask-sse/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── http-api.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── src/graphora/
│   ├── agents/
│   │   ├── graph.py        # + stop callable, checked before model and tool calls
│   │   ├── review.py       # end_reason: `stopped` first
│   │   └── state.py        # EndReason + `stopped`
│   ├── api/
│   │   ├── __init__.py     # create_app(store, runner=None, asks=None)
│   │   ├── ask.py          # AskService, AskRun, body parsing, POST /api/v1/ask
│   │   └── errors.py       # + busy (429, Retry-After), model_unavailable (503)
│   └── cli/__init__.py     # serve: --asks, --model; timeout_graceful_shutdown; AskService.stop()
└── tests/
    ├── unit/test_agents_stop.py          # stop callable and `stopped`
    └── integration/
        ├── test_api_ask.py               # stream, refusals, equality with CLI (db)
        └── test_api_ask_slots.py         # busy, disconnect, keep-alive, jobs unaffected (db)
```

**Structure Decision**: the endpoint lives in `api/ask.py` next to `api/jobs.py` and follows its patterns
(body parsing, `ApiError`, router factory). The 012 change is one keyword and one end reason; no other agent
code changes. Owner: Ulyana (`api/`, `agents/`).

## Complexity Tracking

No constitution violations.
