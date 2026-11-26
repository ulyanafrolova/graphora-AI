# Implementation Plan: Web UI

**Branch**: `019-frontend` | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/019-frontend/spec.md`

## Summary

The whole web UI of `docs/demo` (§ 1–9, § 12, placeholders for § 10–11) in one feature and one PR (team agreement,
issue #40), plus the backend facts the screens need.

What it adds:

- **`frontend/`** (new, shared):
  - React 19 + Vite + TypeScript + Cytoscape.js (R1);
  - screens per `contracts/ui.md`, URL state, typed API client (R8), SSE reader for `/ask` (R9), agent history in
    IndexedDB (R10), large-graph rendering (R11), strict text-only rendering (R12).
- **Backend** (computed by code, same answer on CLI, MCP and HTTP):
  - `components` query: Louvain with seed 0, folder names (R3);
  - `cut` on cycle groups: exact minimum set for ≤ 20 files, greedy above (R4);
  - `GET /api/v1/files` line counts (R5), `GET /api/v1/info` (R6);
  - `graphora serve` serves the built UI with a CSP header and SPA fallback (R7).
- **Infra**: `make web`, `make web-build`, `make web-test`, `make e2e`; CI jobs `frontend` and `e2e`; an e2e server
  with the scripted model (R13).

What it does not change: the graph schema, the store schema, analysis, ingest, history, agents, the verifier.

## Technical Context

**Language/Version**: Python ≥ 3.12 (backend, unchanged); TypeScript 5 strict on Node 22 LTS (frontend)

**Primary Dependencies**:
- backend: none new (NetworkX `louvain_communities`, Starlette `StaticFiles` come with existing pins);
- frontend: react, react-dom, react-router, @tanstack/react-query, cytoscape, cytoscape-fcose, cytoscape-svg,
  d3-hierarchy, shiki, idb; dev: vite, @vitejs/plugin-react, typescript, eslint (+ react, react-hooks, import plugins),
  prettier, vitest, @testing-library/react, msw, @playwright/test, json-schema-to-typescript.

**Storage**: PostgreSQL store of 005, read only (new `list_files` query); browser IndexedDB for agent history.

**Testing**: pytest (golden, integration, `db`, `slow`); Vitest + Testing Library + MSW; Playwright e2e against a real
service with fixtures and the scripted model.

**Target Platform**: `graphora serve` on localhost; desktop Chrome, Firefox, Safari (current versions)

**Project Type**: web application (backend + frontend in one repository)

**Performance Goals**:
- SC-003: 5,000-file snapshot overview < 5 s; expand component / impact toggle < 1 s;
- each backend question already < 0.5 s (018); `components` on 5,000 files < 2 s, cut search bounded (R4).

**Constraints**:
- the UI walks no links (R2, constitution VII), renders all repository/model text as text (R12);
- deterministic backend answers (seeded Louvain, sorted output, bounded searches);
- read-only: the UI starts analyses and asks questions only through existing endpoints;
- one PR: phased tasks, a commit per task, draft PR #41 already open.

**Scale/Scope**: 12 screens (10 real, 2 placeholders), 4 backend additions, graphs up to 5,000 files.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Never execute analyzed code | Pass | The UI shows stored text only; no file is run or evaluated; CSP forbids inline scripts; serving the UI adds static files and no write endpoints (R7, R12) |
| II. Deterministic output | Pass | `components` uses seed 0 and sorted insertion; cuts use fixed order and a fixed budget, the method is reported; answers sorted; golden tests compare two runs. Layout randomness lives only in the view (seeded fcose) and is not part of any fact |
| III. Provenance on every edge | Pass | Code view shows `file:line@commit`, confidence, extractor@version and snippet hash from the stored edges; cut links carry their edges |
| IV. Honest confidence | Pass | Shared legend: heuristic dashed amber, unresolved never drawn as a file link, hypotheses boxed; "history not available" and placeholders instead of invented data |
| V. Facts by code, words by LLM | Pass | Components, cuts, impact, cycles, hotspots come from `graph/queries.py`; the UI only groups and counts answer items (R2); agent claims show the verifier's status |
| VI. Analyzed content is data | Pass | Text-only rendering, `react/no-danger`, hostile-input tests (SC-004) |
| VII. One graph query layer | Pass | New facts live in `graph/queries.py`, served by CLI, MCP and HTTP alike; the frontend has a lint ban on traversal APIs |
| VIII. Golden tests | Pass | Hand-written expected components and cuts for fixtures; byte equality across interfaces; repeat-run tests |

Post-design re-check (after data-model.md and contracts/): unchanged, no exceptions.

## Project Structure

### Documentation (this feature)

```text
specs/019-frontend/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── backend.md          # components, cuts, /files, /info, UI serving
│   └── ui.md               # routes, screens, data sources, visual language, error states
├── checklists/requirements.md
└── tasks.md                # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── src/graphora/
│   ├── graph/queries.py              # components(), cycle cut (Anna)
│   ├── graph/results.py              # Component, ComponentLink, CycleCut, text lines
│   ├── cli/__init__.py               # query … components
│   ├── mcp/server.py                 # components tool, cycles cut
│   ├── api/questions.py              # components row
│   ├── api/routes.py                 # /files, /info (Ulyana's module)
│   ├── api/__init__.py               # UI static files, SPA fallback, CSP (Ulyana's module)
│   └── store/store.py                # list_files (Ulyana's module)
└── tests/
    ├── golden/test_components.py      # hand-written expected components per fixture, CLI = MCP = HTTP
    ├── golden/test_cycle_cuts.py      # hand-written cuts, acyclic after removal, method
    ├── unit/test_cycle_cut.py         # exact vs greedy, budget fallback, ties
    ├── integration/test_ui_api.py     # /files, /info, static UI, SPA fallback, CSP (db)
    ├── integration/test_components_performance.py  # slow
    └── e2e_server.py                  # serve for Playwright: fixtures stored, scripted model, built UI
fixtures/repos/*/expected.json         # + components / cuts written by hand where useful (or separate expected files)
frontend/
├── package.json, package-lock.json, .nvmrc, vite.config.ts, tsconfig.json, eslint.config.js, playwright.config.ts
├── index.html
├── src/
│   ├── main.tsx, App.tsx, routes.tsx
│   ├── api/            # client.ts, types.ts, graph.gen.ts, sse.ts, queries.ts (TanStack hooks)
│   ├── shell/          # Header, Sidebar, SnapshotPicker, Legend, ErrorState
│   ├── graph/          # GraphView, cytoscape styles, layout worker, Minimap, SidePanel, ImpactPanel
│   ├── code/           # CodeView, FileTree, ProvenancePanel, tokens (Shiki)
│   ├── import/         # ImportPage, JobProgress, Coverage
│   ├── insights/       # CyclesPage, HotspotsPage (treemap)
│   ├── agents/         # AskPage, TracePage, history.ts (IndexedDB)
│   ├── integrations/   # McpPage, NotAvailable
│   └── styles/         # tokens.css (colours of the mockups), base.css
└── tests/
    ├── unit/           # Vitest + Testing Library + MSW
    └── e2e/            # Playwright specs per user story
Makefile                               # web, web-build, web-test, e2e
.github/workflows/checks.yml           # + frontend, e2e jobs
CLAUDE.md, README.md                   # commands
```

**Structure Decision**: a web application layout: the existing `backend/` and a new `frontend/`. Backend changes stay in
the modules above; graph facts only in `graph/queries.py`.

## Coordination

- Ulyana reviews the changes in her modules: `api/routes.py` (`/files`, `/info`), `api/__init__.py` (UI serving, CSP),
  `store/store.py` (`list_files`), `graph/results.py` (new types).
- The `cut` field changes the `cycles` answer of CLI, MCP and HTTP (additive). Agents that read `cycles` (012) are
  unaffected; the verifier ignores unknown fields.
- PR #41 is stacked on #39; after #39 merges, its base becomes `main`.
- `docs/demo/README.md` stays the concept; README gets a "Web UI" section with the two run modes.

## Commits

- One commit per task of tasks.md, short lowercase English messages; push at the end of each phase.
- This plan is committed as `plan: 019 frontend`.

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| One PR for the whole UI plus backend additions | Team agreement (issue #40) | Several PRs: rejected by the team; mitigated by phased tasks, a commit per task, the draft PR open from the start |
| Second toolchain (Node/npm) in the repository and CI | The constitution fixes React + Vite + TypeScript | None: a frontend needs it; kept to one lockfile and one CI job pair |
