# Quickstart: Graph Queries over HTTP

## Prerequisites

```bash
make db
export GRAPHORA_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora
export GRAPHORA_TEST_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora_test
cd backend && uv sync
```

## Store a snapshot and serve it

```bash
uv run graphora analyze ../fixtures/repos/ts-app/repo --store --out /tmp/g.json
uv run graphora serve
curl -s localhost:8000/api/v1/repositories        # note the repository name and snapshot id
```

## Ask questions

```bash
B='localhost:8000/api/v1'; Q='repository=<name>&snapshot=<id>'
curl -s "$B/overview?$Q"
curl -s "$B/impact?$Q&target=<path>&limit=5"
curl -s "$B/neighbors?$Q&target=<path>"
curl -s "$B/cycles?$Q"
curl -s "$B/definitions?$Q&name=<Symbol>"
```

Expected: each body equals the CLI answer, e.g.

```bash
diff <(curl -s "$B/impact?$Q&target=<path>&limit=5") \
     <(uv run graphora query /tmp/g.json impact <path> --limit 5 --format json) && echo same
```

Errors (contracts/http-api.md): `curl -s "$B/cycles?$Q&symbol=x"` → 400; `…&target=nope.py` → 404 with the reason;
`limit=501` → 400. The routes and their parameters are listed at `localhost:8000/api/v1/docs`.

## Tests

```bash
uv run pytest tests/golden/test_http_queries.py tests/integration/test_http_queries_api.py   # db
uv run pytest -m slow tests/integration/test_http_queries_performance.py                     # SC-003
uv run pytest                                                                                # SC-006
```
