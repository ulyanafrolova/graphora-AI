# Quickstart: checking hotspots end to end

Shapes are in contracts/interfaces.md and contracts/graph-schema-v8.md. Commands run from `backend/`.

## Prerequisites

```
uv sync
make db                                   # only for the store and HTTP steps
export GRAPHORA_TEST_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora_test
export GRAPHORA_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora
```

## 1. Automated checks

```
uv run pytest -m "not db and not slow" -k "history or hotspot"   # reader, query, CLI, verifier, fetch (local server)
uv run pytest -m db -k "history or hotspot"                       # store reuse rule, HTTP endpoint, jobs
uv run pytest -m slow -k history                                  # SC-003: 10,000 commits, 5,000 files
make check                                                        # whole suite, PostgreSQL running
```

Expected: everything passes. The golden fixtures all show `history: not_available (no_git)`.

## 2. Local git folder (US1)

```
uv run graphora analyze .. --out /tmp/self.json      # the Graphora repository itself
uv run graphora query /tmp/self.json hotspots
```

Expected:
- the stderr info line ends with `history: N commits from … to …`;
- the list is ranked by score;
- running `analyze` again gives a byte-identical `/tmp/self.json` (`cmp`).

## 3. Honest missing history (US2)

```
uv run graphora analyze ../fixtures/repos/py-flat/repo --out /tmp/flat.json
uv run graphora query /tmp/flat.json hotspots                 # history: not available (no_git), total: 0
uv run graphora analyze .. --no-history --out /tmp/nohist.json
uv run graphora query /tmp/nohist.json hotspots               # not available (skipped by request)
```

For a dirty tree (uncommitted change in the repository), the answer adds `uncommitted changes not counted`.

## 4. GitHub (manual, needs network)

```
uv run graphora analyze https://github.com/pallets/click --out /tmp/click.json
uv run graphora query /tmp/click.json hotspots --limit 5
```

Expected:
- the history line shows commits of the year before the fetched commit;
- the run takes well under a minute (SC-003a);
- a second run gives the same bytes.

The fallbacks (`too_large`, `time_limit`, `fetch_failed`) are checked by the automated tests against a local
server (step 1), not here.

## 5. Store, MCP and HTTP (US3)

```
uv run graphora analyze .. --store
uv run graphora serve &
curl 'localhost:8000/api/v1/hotspots?repository=graphora-AI&snapshot=<sha>&limit=5'
uv run graphora mcp --repository graphora-AI --snapshot <sha>    # call the hotspots tool from an MCP client
```

Expected: the HTTP body equals `graphora query … hotspots --format json` for the same snapshot and limit, and
the MCP tool lists the same items.

## 6. Verifier

In a Python shell, check two claims against the analysis of step 2 and the real top hotspot:

- a `query` claim with `question: "hotspots"`, `member`, `metric: "commits"` and the right value gives
  `verified`;
- the same claim with `value + 1` gives `rejected` / `count_mismatch` with hint `actual N`.
