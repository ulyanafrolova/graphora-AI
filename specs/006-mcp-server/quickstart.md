# Quickstart: MCP Server

How to check that 006 works end to end. Contracts: [mcp-tools.md](contracts/mcp-tools.md),
[cli.md](contracts/cli.md).

## Setup

```
cd backend && uv sync
```

## Tests

```
uv run pytest -m "not slow and not db"            # offline, no database
uv run pytest tests/golden/test_mcp_queries.py     # MCP answers equal `graphora query` on every fixture
uv run pytest -m db tests/integration/test_mcp_store.py   # store mode; needs `make db` and GRAPHORA_TEST_DATABASE_URL
uv run pytest tests/integration/test_mcp_performance.py   # SC-003, marked slow
make check
```

## Manual scenarios

```
uv run graphora analyze ../fixtures/repos/py-cycles/repo --out /tmp/cycles.json
```

| # | Action | Expected |
|---|---|---|
| 1 | `uv run graphora query /tmp/cycles.json overview` | snapshot, languages, file counts, unresolved imports |
| 2 | `uv run graphora query /tmp/cycles.json definitions main` | `user.py`, line 5, kind `function` |
| 3 | `claude mcp add graphora -- uv run --directory "$PWD" graphora mcp --graph /tmp/cycles.json` (from `backend/`) | `claude mcp list` shows `graphora` as connected |
| 4 | In Claude Code: "Using graphora, what breaks if I change loop/a.py?" | the agent calls `impact`; the answer lists the files from `py-cycles/queries.json` with `file:line` chains |
| 5 | In Claude Code: "Using graphora, are there import cycles?" | the agent calls `cycles`; three groups as in `queries.json` |
| 6 | `uv run graphora mcp --graph /tmp/missing.json; echo $?` | error on standard error, exit 2 |
| 7 | `echo '{}' > /tmp/bad.json; uv run graphora mcp --graph /tmp/bad.json; echo $?` | exit 7 |
| 8 | With `make db`: `uv run graphora analyze ../fixtures/repos/py-flat/repo --store`, then `claude mcp add graphora-store -- uv run --directory "$PWD" graphora mcp --repository repo --snapshot <id>` | `read_lines` is listed; asking for `pkg/a.py` lines 1–5 returns them marked as file content |
| 9 | `claude mcp remove graphora` (and `graphora-store`) | clean up |

For scenario 8 a local folder is stored under its folder name (`repo`); take the snapshot id from `curl -s 127.0.0.1:8000/api/v1/repositories`
with `uv run graphora serve` running, or from the `analyze --store` message.

## Done when

- Every MCP graph answer equals `graphora query --format json` on every fixture (SC-001).
- Scenario 4 works in Claude Code on the first try (SC-002).
- The performance test passes on a 5,000-file synthetic graph (SC-003).
