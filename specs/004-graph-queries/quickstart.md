# Quickstart: Graph Queries

How to check that 004 works end to end. Contracts: [cli.md](contracts/cli.md),
[answers.md](contracts/answers.md), [queries-api.md](contracts/queries-api.md).

## Setup

```
cd backend && uv sync
```

## Tests

```
uv run pytest -m "not slow"                       # everything except performance
uv run pytest tests/golden/test_queries.py        # hand-checked answers for every fixture
uv run pytest tests/integration/test_query_performance.py   # SC-004, marked slow
make check                                        # lint + tests, as in CI
```

## Manual scenarios

Build a graph once:

```
uv run graphora analyze ../fixtures/repos/py-cycles/repo --out /tmp/cycles.json
uv run graphora analyze ../fixtures/repos/ts-barrels/repo --out /tmp/barrels.json
```

| # | Command | Expected |
|---|---|---|
| 1 | `uv run graphora query /tmp/cycles.json cycles` | the groups from `py-cycles/queries.json`, each with a cycle of `file:line` links; exit 0 |
| 2 | `uv run graphora query /tmp/cycles.json impact <file> --max-depth 1` | only distance-1 dependents; the last lines show the depth limit and the completeness note |
| 3 | `uv run graphora query /tmp/barrels.json dependents <defining file>` then add `--follow-barrels` | without the flag only the barrel is listed; with it the real importers appear, each with the import line and the re-export lines |
| 4 | `uv run graphora query /tmp/barrels.json cycles --no-type-only` | the loop through type-only imports disappears |
| 5 | `uv run graphora query /tmp/cycles.json key-files --format json` | JSON as in `answers.md`; running it twice gives identical bytes (`cmp`) |
| 6 | `uv run graphora query /tmp/cycles.json dependents no/such.py` | exit 7, message `no/such.py is not in snapshot …` |
| 7 | `echo '{}' \| uv run graphora query - cycles` | exit 6, invalid graph document |
| 8 | `uv run graphora analyze ../fixtures/repos/ts-app/repo \| uv run graphora query - dependents react` | files importing `react`, each with its import lines |

## Done when

- Golden query tests pass for all fixtures, and a repeated run gives identical bytes (constitution VIII).
- Every cited edge in every golden answer exists in the graph with the same `id` (SC-002).
- The performance test passes on a 5,000-file synthetic graph (SC-004).
