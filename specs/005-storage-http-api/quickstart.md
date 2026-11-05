# Quickstart: validate 005 storage and HTTP API

Contracts: [cli.md](contracts/cli.md), [http-api.md](contracts/http-api.md), [store-api.md](contracts/store-api.md).

## Prerequisites

- Docker (for PostgreSQL 17), `uv`, Python 3.12.
- From the repository root:

```
make db                                   # docker compose up -d postgres (127.0.0.1:5432)
export GRAPHORA_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora
export GRAPHORA_TEST_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora_test
cd backend && uv sync
```

## 1. Test suite

```
uv run pytest                     # everything, including `db` tests
uv run pytest -m "not db"         # no database: every pre-005 test still passes (SC-007)
```

Expect: all pass. Without `GRAPHORA_TEST_DATABASE_URL`, `db` tests fail with a hint to run `make db`.

## 2. Store and read back (US1, SC-001)

```
uv run graphora analyze ../fixtures/repos/py-flat/repo --store --out /tmp/a.json
uv run graphora analyze ../fixtures/repos/py-flat/repo --out /tmp/b.json
cmp /tmp/a.json /tmp/b.json
uv run graphora analyze ../fixtures/repos/py-flat/repo --store --out /tmp/c.json
```

Expect: first run prints `graphora: info: stored repo content:…`, `cmp` prints nothing, third run prints
`graphora: info: reused repo content:…`.

## 3. Serve and read (US2)

```
uv run graphora serve &
curl -s 127.0.0.1:8000/api/v1/repositories
curl -s '127.0.0.1:8000/api/v1/graph?repository=repo&snapshot=content:<hash>' | cmp - /tmp/b.json
curl -s '127.0.0.1:8000/api/v1/file?repository=repo&snapshot=content:<hash>&path=<a coverage path>&start=1&end=3'
curl -s -o /dev/null -w '%{http_code}\n' '127.0.0.1:8000/api/v1/file?repository=repo&snapshot=content:<hash>&path=../../etc/passwd'
```

Expect: the repository list includes `repo`; the graph is byte-identical; the file shows lines 1–3 with
numbers; the traversal path returns `404`.

## 4. Restart (US1 scenario 4, SC-003)

Stop the server and `docker compose restart postgres`, start `graphora serve` again and repeat step 3.
Expect identical output.

## 5. GitHub reuse (SC-002)

Covered offline by `tests/integration/test_store_cli.py` with `tests/fake_github.py`: the second
`--store` run of the same commit makes one API request and zero archive downloads.

## 6. Clean up

```
kill %1; make db-down
```
