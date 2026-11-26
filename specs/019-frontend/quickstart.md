# Quickstart: Web UI

## Prerequisites

```bash
make db                                   # PostgreSQL 17
export GRAPHORA_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora
export GRAPHORA_TEST_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora_test
cd backend && uv sync && cd ..
cd frontend && npm ci && cd ..           # Node 22 (see frontend/.nvmrc)
```

## Develop (two processes)

```bash
cd backend && uv run graphora serve       # API on 127.0.0.1:8000
make web                                  # UI on http://localhost:5173, /api proxied to :8000
```

## Demo (one process, FR-025)

```bash
make web-build                            # writes frontend/dist
cd backend && uv run graphora serve       # open http://127.0.0.1:8000
```

## Validate the user stories by hand

1. **US2 Import**: open `/import`, paste `https://github.com/<owner>/<small public repo>` or drop
   `fixtures` ZIP; watch stages to `done`; click "Open graph".
2. **US1**: graph opens at System level; expand a component; click a file; turn on impact; open Code & provenance on
   an import line and compare the provenance with
   `uv run graphora query <graph.json> dependencies <path> --format json`.
3. **US3**: Cycles on a `py-cycles` snapshot shows the cut with method `exact`; Hotspots on a local git analysis
   shows tiles; on a ZIP snapshot "history not available (zip)".
4. **US4**: with Ollama running (`ollama serve`, model `qwen3:8b`), ask "What breaks if I change <path>?"; reload;
   the answer is in the history; Agent trace shows its steps.
5. **US5**: store a large repository (or the 5,000-file test graph) and check the overview opens in < 5 s.
6. **US6**: MCP page lists the tools of `/api/v1/info`; PR impact and Security show "not available in this version".

## Tests

```bash
cd backend && uv run pytest -m "not llm"                 # backend incl. components, cuts, /files, /info, UI serving
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
make e2e                                                 # Playwright against tests/e2e_server.py (scripted model)
```
