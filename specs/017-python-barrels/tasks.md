---

description: "Task list for 017-python-barrels"
---

# Tasks: Python Barrel Following

**Input**: Design documents from `specs/017-python-barrels/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R6), data-model.md, contracts/graph-format.md,
contracts/queries.md, quickstart.md

**Tests**: Required (constitution VIII). Within each phase, write the tests first and confirm they fail.

**Organization**: Phase 2 (graph format v7 with `alias`) blocks every story. Then:

- US1 (P1): see who really uses a name behind `__init__.py` (`dependents --follow-barrels`);
- US2 (P1): renamed imports are followed exactly;
- US3 (P2): `impact --follow-barrels` sees through Python packages.

Paths are relative to the repository root. Code lives in `backend/src/graphora/`, tests in `backend/tests/`.
Run commands from `backend/`. Keep comments minimal, in the style of the existing modules. `expected.json` and
`queries.json` are written by hand from the fixture source, never copied from tool output.

**Commits**: commit after each task group marked **Commit**; push at the end of each phase.

## Fixture `py-barrels` (used by all phases)

```text
fixtures/repos/py-barrels/repo/
├── app.py          1 from pkg import AuthService
│                   2 from pkg import make_server
│                   3 from pkg import tool
│                   4 from pkg import LIMIT
│                   5 from pkg import version
├── old.py          1 from pkg import create_server
│                   2 from pkg import nothing
├── cli.py          1 from pkg.auth import AuthService
├── run.py          1 from pkg import server
└── pkg/
    ├── __init__.py 1 from .auth import AuthService
    │               2 from .server import create_server as make_server
    │               3 from .tools import *
    │               4 from .config import LIMIT
    │               5 from .missing import nothing
    │               6 from . import server
    │               7 (empty)
    │               8 def version():
    │               9     return "1"
    ├── auth/__init__.py   1 from .service import AuthService
    ├── auth/service.py    class AuthService (line 1)
    ├── server.py          def create_server() (line 1)
    ├── tools.py           def tool() (line 1)
    └── config.py          LIMIT = 10
```

## Phase 1: Setup

- [x] T001 Create the fixture source files above in `fixtures/repos/py-barrels/repo/` (exact lines as listed;
  each function body `return None` or `pass`).

## Phase 2: Foundational — graph format v7 with `alias` on Python imports

**Goal**: FR-001–FR-004, FR-013. Python import edges carry the `as` name; every consumer accepts v7.

- [x] T002 [P] Tests in `backend/tests/unit/test_extract.py`: `from .x import f as g` gives name `f` with alias
  `g`; `from .x import f` and `from .x import f as f` give alias `None`; `import a.b as c` gives alias `c`;
  `import a.b` gives `None`; `from .x import *` gives `None`.
- [x] T003 [P] Tests in `backend/tests/unit/test_model.py` (or the existing edge-validation test module):
  `alias` is accepted on an `imports` edge whose extractor starts with `python-adapter@`, rejected on an
  `imports` edge from `js-adapter@…`, and rules for `reexports` / `using_alias` / `type_reference` are unchanged.
- [x] T004 Add `aliases: tuple[str | None, ...]` to `ImportRecord` in
  `backend/src/graphora/adapters/python/extract.py` (one per name; `None` when there is no `as` or the `as` name
  equals the default); fill it in `_import_statement` and `_from_statement`; bump `VERSION` to `0.4.0` in
  `backend/src/graphora/adapters/python/__init__.py` and add the new fingerprint line to
  `backend/tests/unit/extractor_versions.json`.
- [x] T005 Carry the alias to the edge in `_python_graph` in `backend/src/graphora/graph/build.py` (resolver
  targets are one per name, in `names` order; `import` records have one name).
- [x] T006 Allow `alias` on Python `imports` edges in `Edge.__post_init__` in `backend/src/graphora/graph/model.py`
  ("`alias` present → `type` is `reexports`, or `directive` is `using_alias`, or (`type` is `imports` and
  `extractor` starts with `python-adapter@`)").
- [x] T007 Schema v7 in `schema/graph.schema.json` (`schema_version` const 7, description "Schema version 7",
  `alias` rule extended as in contracts/graph-format.md) and `SCHEMA_VERSION = 7` in
  `backend/src/graphora/graph/serialize.py`; update tests that pin version 6
  (`tests/unit/test_overview.py`, `tests/unit/test_serialize.py`, `tests/integration/test_store.py`, others found
  by `grep -rn "schema_version" tests`).
- [x] T008 Add schema accept/reject samples for the new `alias` rule next to the existing schema tests.
- [x] T009 Drop `alias` in the v1 projection of `test_python_fixtures_match_v1` in
  `backend/tests/golden/test_fixtures.py`.
- [x] T010 Add `"alias"` by hand to the Python edges with `as` in `fixtures/repos/py-src-layout/expected.json`,
  `fixtures/repos/py-dynamic/expected.json` and `fixtures/repos/mixed-fullstack/expected.json` (find them with
  `grep -rn " as " fixtures/repos/*/repo --include='*.py'`).
- [x] T011 Write `fixtures/repos/py-barrels/expected.json` by hand (nodes, edges with `alias` on
  `pkg/__init__.py:2`, unresolved `pkg.missing`, coverage).
- [x] T012 Run `uv run pytest -m "not db"`; all pass. **Commit** "record python import aliases (schema v7)"; push.

**Checkpoint**: graphs carry `alias`; no query change yet; every answer is unchanged.

## Phase 3: User Story 1 — dependents see through `__init__.py` (P1) 🎯 MVP

**Goal**: FR-005–FR-010. **Independent test**: `queries.json` dependents cases on `py-barrels`.

- [x] T013 [P] [US1] Unit tests in `backend/tests/unit/test_queries.py` (or the barrel test module) on a small
  in-memory Python graph: one-package re-export, two-package chain, name defined in `__init__.py`, `*` import,
  unresolved import, constant (`LIMIT`) stops at `config.py`, loop of two `__init__.py` stops, symbol filter,
  `follow_barrels` off unchanged, a re-import through an ordinary module (`a.py` imports `helper` from `b.py`,
  `c.py` imports it from `a.py`), and `import x.y as z` re-imported as `z` stops at `x/y.py`.
- [x] T014 [US1] Python branch of `_trace` in `backend/src/graphora/graph/queries.py` (research § R3): index
  Python `imports` edges by source (static, not `unresolved`, `file:` target, symbol not `*`, bound name
  `alias or symbol`); a Python file stops when a top-level `class`/`function` definition has the name, else
  follows the first matching edge in sort order, falling back to the edge's target; `import a.b as c` stops at
  the target. Keep the TS/JS branch as is. Update the `_trace` docstring.
- [x] T015 [US1] `fixtures/repos/py-barrels/queries.json` by hand: dependents of `pkg/auth/service.py`,
  `pkg/config.py`, `pkg/tools.py` with and without `follow_barrels`, and with `symbol: "AuthService"`.
- [x] T016 [US1] Run the unit and golden query tests. **Commit** "follow python package imports in dependents".

## Phase 4: User Story 2 — renamed imports (P1)

**Goal**: US2. **Independent test**: `queries.json` cases for `pkg/server.py`.

- [x] T017 [US2] Add to `fixtures/repos/py-barrels/queries.json`: dependents of `pkg/server.py` with
  `follow_barrels` lists `app.py` (via `pkg/__init__.py:2`) and `pkg/__init__.py`, not `old.py`; with
  `symbol: "create_server"` lists only `pkg/__init__.py`.
- [x] T018 [US2] Unit test in `backend/tests/unit/test_queries.py`: `from .x import f, f as g` (two edges), an
  importer of `g` and an importer of `f` both attach to `x.py`.
- [x] T019 [US2] Run tests. **Commit** "cover renamed python imports"; push.

## Phase 5: User Story 3 — impact (P2)

- [x] T020 [US3] Add impact cases to `fixtures/repos/py-barrels/queries.json`: `pkg/auth/service.py` with
  `follow_barrels` (`app.py` and `cli.py` at distance 1 with the barrel link), and without (as today).
- [x] T021 [US3] Run tests. **Commit** "check python barrels in impact".

## Phase 6: Polish

- [ ] T022 [P] Help texts: CLI `--follow-barrels` in `backend/src/graphora/cli/__init__.py` and the
  `dependents` / `impact` descriptions in `backend/src/graphora/mcp/server.py` (contracts/queries.md).
- [ ] T023 [P] MCP golden check: the new `queries.json` cases pass through MCP (`tests/golden/test_mcp_queries.py`
  picks them up; confirm).
- [ ] T024 [P] Performance: add a Python package re-export layer to the generated repo in
  `backend/tests/integration/test_query_performance.py` (or confirm it already exercises barrels) and keep the
  limits (SC-005).
- [ ] T025 Docs: `grep -rn "barrel" docs README.md`; where barrel following is described as TS/JS-only, add
  Python package imports. `specs/004-graph-queries` is not edited.
- [ ] T026 Run quickstart.md steps 2–5 and record the SC-001 result (7 files) in research.md § Implementation
  notes; `make check` with PostgreSQL. **Commit** "polish python barrel following"; push; mark PR #26 ready.

## Dependencies

Phase 1 → Phase 2 → US1 → US2 → US3 → Polish. US2 and US3 only add cases on top of the US1 tracing code.

## Parallel opportunities

T002/T003 (different test files); T022/T023/T024.

## Implementation strategy

MVP = Phases 1–3: after them the `create_server` question already gets the full answer.
