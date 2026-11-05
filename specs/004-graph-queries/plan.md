# Implementation Plan: Graph Queries

**Branch**: `004-graph-queries` | **Date**: 2026-11-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-graph-queries/spec.md`

## Summary

This slice adds the one graph query layer that later features call (HTTP API, MCP in 006, agent tools and
the verifier in 008). It works on the graph document written by `graphora analyze` and never touches the
analyzed repository.

What it adds:

- **Loading.** `graph/load.py` reads a graph JSON back into the existing model and validates it (R2).
- **Queries.** `graph/queries.py` builds a NetworkX index once and answers six questions: dependencies,
  dependents (with a symbol filter), impact (with a depth limit), neighbors, cycles and key files (R3–R7).
  Barrel following is an option for dependents and impact (R8).
- **Answers.** `graph/results.py` holds frozen answer types, canonical JSON and readable text (R11). Every
  item carries the real graph edges it rests on, its weakest confidence and its type-only mark, and every
  answer carries the snapshot id, the options and a completeness note (R9).
- **CLI.** `graphora query <graph> <question> [target] [options]` (contracts/cli.md).

What it does not change: the graph schema (v2), the analyzer, existing fixtures' `expected.json`.

## Technical Context

**Language/Version**: Python ≥ 3.12 (unchanged)

**Primary Dependencies**: adds `networkx==3.7` (R1). No new dev dependencies.

**Storage**: none. Input is a graph JSON file or standard input; output is standard output

**Testing**: pytest. Golden query answers per fixture (`fixtures/repos/<name>/queries.json`), two new fixtures
(`py-cycles`, `ts-barrels`), unit tests on synthetic documents (heuristic edges, ties, limits), a CLI
integration test and a slow performance test (R12)

**Target Platform**: developer laptop (macOS, Linux) and CI, offline

**Project Type**: library module + CLI subcommand in the existing backend

**Performance Goals**: SC-004 — load a 5,000-file graph in < 2 s, each query in < 1 s after loading

**Constraints**: byte-identical answers (FR-015); read-only; no file system access except reading the graph
file in the CLI; no network

**Scale/Scope**: graphs up to the ingest limits (5,000 files, tens of thousands of edges)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Never execute analyzed code | Pass | queries read only the graph document; no repository access |
| II. Deterministic output | Pass | sorted insertion into NetworkX, fixed tie-breaks (R5, R6), canonical JSON; determinism test per fixture |
| III. Provenance on every edge | Pass | answers cite graph edges verbatim, with `id`; derived links are lists of real edges, never new edges (FR-011) |
| IV. Honest confidence | Pass | weakest-link confidence, heuristic = "likely", unresolved never traversed, completeness note (R4, R9) |
| V. Facts by code | Pass | cycles, dependents, impact and centrality computed by algorithms; no model involved |
| VI. Analyzed content is data | Pass | no file contents are read; limits bound answer size for later model use (FR-016) |
| VII. One graph query layer | Pass | all queries in `backend/src/graphora/graph/`; schema unchanged |
| VIII. Golden tests | Pass | hand-written `queries.json` per fixture; new fixtures with hand-written `expected.json` |

Post-design re-check: still passes. No deviations, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/004-graph-queries/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── queries-api.md
│   ├── answers.md
│   └── cli.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml                    # + networkx==3.7
├── src/graphora/
│   ├── graph/
│   │   ├── load.py                   # new: loads(bytes) -> GraphDocument, InvalidGraph
│   │   ├── queries.py                # new: index, resolve, six queries, barrel following
│   │   └── results.py                # new: answer types, dumps, render_text
│   └── cli/__init__.py               # + `query` subcommand (shared module, Ulyana reviews)
└── tests/
    ├── unit/test_load.py             # validation errors, round trip
    ├── unit/test_queries.py          # synthetic graphs: heuristic, ties, limits, type-only, barrels
    ├── golden/test_queries.py        # fixtures/repos/*/queries.json
    ├── integration/test_query_cli.py # exit codes, text/json, stdin
    └── integration/test_query_performance.py  # slow, SC-004

fixtures/repos/
├── py-cycles/{repo/, expected.json, queries.json}    # new fixture
├── ts-barrels/{repo/, expected.json, queries.json}   # new fixture
└── <existing>/queries.json                           # new files; expected.json untouched
```

**Structure Decision**: everything lives in the existing backend package. Queries go into `graph/`, which the
constitution names as the only place for graph queries. `serialize.py` and `model.py` (Ulyana's) are reused
as they are.

## Coordination

- `cli/__init__.py`, `pyproject.toml` and the two new fixtures are shared or owned by Ulyana: the PR requests
  her review. 005 (PR #11) also edits `cli/__init__.py` (`--store`, `serve`): rebase on `main` before review
  and keep the `query` subcommand in its own function to keep the conflict small.
- 006 (MCP) will call `queries-api.md` directly; the answer JSON is its tool output format.

## Open item

- Clarify question 1 (symbol-scoped impact) was not answered. The plan follows the spec as written; adding
  `symbol=` to `impact` later is a small change (research.md § Open item).

## Complexity Tracking

No constitution violations.
