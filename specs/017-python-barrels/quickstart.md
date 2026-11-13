# Quickstart: Python Barrel Following

From `backend/`.

| # | Do | Expect |
|---|---|---|
| 1 | `uv run pytest -m "not db"` | all pass |
| 2 | `uv run graphora analyze ../fixtures/repos/py-barrels/repo --out /tmp/pyb.json` | `schema_version` 7; the `as` edge in `pkg/__init__.py` has `"alias"` |
| 3 | `uv run graphora query /tmp/pyb.json dependents pkg/service.py` | `pkg/__init__.py` only (as before) |
| 4 | same with `--follow-barrels` | also the files importing through `pkg`, chains cite both lines |
| 5 | `uv run graphora analyze . --out /tmp/self.json`, then `uv run graphora query /tmp/self.json dependents src/graphora/mcp/server.py --symbol create_server --follow-barrels` | `mcp/__init__.py` plus the 6 importers through `graphora.mcp` (SC-001) |
| 6 | Claude Code: `claude mcp add graphora -- uv run --directory "$PWD" graphora mcp --graph /tmp/self.json`; ask "using Graphora what depends on create_server? follow barrels" | same 7 files |
| 7 | `make check` with PostgreSQL | all pass |
