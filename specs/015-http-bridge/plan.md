# Implementation Plan: HTTP Bridge Between Frontend Calls and Backend Routes

**Branch**: `015-http-bridge` | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/015-http-bridge/spec.md`

## Summary

The analyzer links frontend HTTP calls to backend routes in the same repository. The Python adapter also
records FastAPI/Flask route decorators and router/blueprint prefixes (R2); the JS/TS adapter also records
`fetch`/`axios` calls and top-level string constants (R3); a new resolver `resolve/http.py` applies literal
prefixes, normalizes paths and matches calls to routes, with "literal beats parameter" and file-level ambiguity
(R4). Matches become `http_call` edges, `heuristic` with reason `http_route`, carrying `METHOD path` as symbol and
the route line; unmatched calls become `unresolved:http:` edges with reasons `dynamic`, `not_found`, `ambiguous`
(R5). Graph schema goes to v9 with every consumer and fixture updated in this change (R6, R7).

## Technical Context

**Language/Version**: Python ≥ 3.12 (unchanged)

**Primary Dependencies**: none new; Tree-sitter Python and TypeScript/JavaScript grammars already used

**Storage**: unchanged; stored v8 analyses are not reused and are re-analyzed on demand (version check)

**Testing**: pytest; unit tests for normalization, matching and extraction; golden tests over the new
`http-bridge` fixture and all existing fixtures; schema contract tests; the existing performance test

**Target Platform**: the analyzer (CLI, pipeline, `serve` jobs)

**Project Type**: analyzer extension plus a graph contract change

**Performance Goals**: SC-004: analysis time of every fixture and the performance repository +10% at most

**Constraints**: static only (no code run, no config/env read); deterministic; never guess a target

**Scale/Scope**: thousands of files; calls matched against routes bucketed by method and segment count (R8)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Never execute analyzed code | Pass | decorators and calls are read from the syntax tree; no import, no config or env read (FR-010) |
| II. Deterministic output | Pass | facts in file order, routes sorted, edges sorted by the existing key; golden repeat test |
| III. Provenance on every edge | Pass | HTTP edges carry call line, column, snapshot, extractor `http-bridge@…`, snippet hash, plus `route_line` |
| IV. Honest confidence | Pass | matches are only `heuristic`; dynamic, unmatched and ambiguous calls are `unresolved` with a reason; no edge to a guessed file |
| V. Facts by code, words by LLM | Pass | matching is code; agents see HTTP links as likely; the verifier marks them `heuristic` |
| VI. Analyzed content is data | Pass | unchanged |
| VII. One graph query layer | Pass | no new query code; schema v9 with all consumers and fixtures in this PR |
| VIII. Golden tests | Pass | new `http-bridge` fixture with hand-written `expected.json`; existing fixtures re-checked |

Post-design re-check: still passes. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/015-http-bridge/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── graph-schema-v9.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
schema/graph.schema.json                     # v8 → v9
fixtures/repos/http-bridge/                  # new: repo/backend, repo/frontend, expected.json (by hand)
fixtures/repos/*/expected.json               # mixed-fullstack gains its not_found call (version 9 comes from the serializer)
backend/
├── src/graphora/
│   ├── adapters/python/extract.py           # + RouteFact, RouterFact, MountFact
│   ├── adapters/python/__init__.py          # VERSION bump
│   ├── adapters/js/extract.py               # + HttpCallFact, constants
│   ├── adapters/js/__init__.py              # VERSION bump
│   ├── resolve/http.py                      # new: routes, normalize, call_path, match, HTTP_VERSION
│   ├── graph/model.py                       # http_call, http_route, http ecosystem, Edge.route_line
│   ├── graph/serialize.py                   # SCHEMA_VERSION = 9, route_line
│   ├── graph/load.py                        # route_line
│   └── graph/build.py                       # _http_graph, extractors
└── tests/
    ├── unit/test_http_normalize.py
    ├── unit/test_http_extract.py
    ├── unit/test_http_match.py
    ├── contract/test_schema.py              # v9 samples
    └── golden/test_fixtures.py              # picks up the new fixture
```

**Structure Decision**: extraction stays in the adapters (one parse per file), linking in `resolve/` like import
resolution, graph assembly in `graph/build.py`. All touched modules are Ulyana's (`adapters/`, `resolve/`,
`graph/build.py`, `graph/model.py`, `graph/serialize.py`, `schema/`); `graph/queries.py` and `verify/` (Anna's)
get tests only, no code change.

## Complexity Tracking

No constitution violations.
