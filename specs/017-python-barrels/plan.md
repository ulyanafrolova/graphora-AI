# Implementation Plan: Python Barrel Following

**Branch**: `017-python-barrels` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/017-python-barrels/spec.md`

## Summary

The Python adapter writes the name bound by `as` on Python import edges (`alias`), and the graph format moves to
version 7 to allow it. The query layer gets a Python branch in barrel tracing: a Python file passes a name on
when it imports it explicitly under that bound name, and the trace stops at the file that defines the name, or
at the last file a resolved import points to. Derived links reuse the 004 barrel-link machinery unchanged, so
`dependents`, `impact`, the CLI and MCP pick it up without new code paths.

## Technical Context

**Language/Version**: Python 3.12 (`uv`)

**Primary Dependencies**: Tree-sitter (`tree-sitter-python`, already pinned), NetworkX; no new dependencies

**Storage**: PostgreSQL store (005) keeps whole graph documents; no table change

**Testing**: pytest; golden fixtures in `fixtures/repos/`, query fixtures `queries.json`

**Target Platform**: CLI, HTTP API, MCP server (stdio)

**Project Type**: CLI + library + services

**Performance Goals**: barrel links on 1,000 Python files within the existing 004 query performance test

**Constraints**: deterministic output; no guessing (constitution II, IV)

**Scale/Scope**: about 6 source files, 1 new fixture, 3–4 updated `expected.json`

## Constitution Check

| Principle | Check |
|---|---|
| I. Never execute analyzed code | Pass. Only Tree-sitter parsing; queries read the graph. |
| II. Deterministic output | Pass. `alias` is part of the edge sort key and id already; traces walk edges in sorted order. |
| III. Provenance on every edge | Pass. No new edges; derived links cite the stored import edges. |
| IV. Honest confidence | Pass. Only explicit `from … import` bindings are followed; `*` and unresolved imports are not; link confidence is the weakest of its edges. |
| V. Facts by code | Pass. Pure query code. |
| VII. One graph query layer | Pass. Tracing lives in `graph/queries.py`; schema bump to v7 with all consumers in this change. |
| VIII. Golden tests | Pass. New hand-written `py-barrels` fixture with `expected.json` and `queries.json`. |

Shared files (`schema/graph.schema.json`, `expected.json`) and Ulyana's module (`adapters/python`) change in
this feature's pull request, as in PR #22; the pull request needs her agreement before merge.

Post-design re-check: still passes; no deviations, Complexity Tracking not needed.

## Project Structure

### Documentation (this feature)

```text
specs/017-python-barrels/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── graph-format.md
│   └── queries.md
└── tasks.md
```

### Source Code (repository root)

```text
schema/graph.schema.json                 v7: `alias` allowed on Python `imports` edges
backend/src/graphora/
├── adapters/python/extract.py           ImportRecord: alias per imported name
├── adapters/python/__init__.py          adapter version 0.4.0
├── graph/build.py                       Edge(alias=…) for Python edges
├── graph/model.py                       Edge validation: alias on Python imports
├── graph/serialize.py                   SCHEMA_VERSION = 7
├── graph/queries.py                     Python branch in _trace / _barrel_links
├── cli/__init__.py, mcp/server.py       follow_barrels help text
backend/tests/
├── unit/                                extract alias, model validation, Python tracing
├── golden/test_fixtures.py, v1/         v1 projection ignores `alias`
fixtures/repos/py-barrels/               new: repo/, expected.json, queries.json
fixtures/repos/{py-src-layout,py-dynamic,mixed-fullstack}/expected.json   `alias` on `as` imports
```

**Structure Decision**: existing backend layout; no new modules.
