# Quickstart: HTTP Bridge

Validation guide for 015. Contract: [contracts/graph-schema-v8.md](contracts/graph-schema-v8.md).

## Prerequisites

```
cd backend && uv sync
```

## 1. Tests

```
uv run pytest -m "not db and not slow"
uv run pytest tests/integration/test_performance.py    # SC-004, compare with main
```

Expected: all pass. They cover normalization and matching (unit), extraction of routes and calls (unit), the
`http-bridge` fixture against its hand-written `expected.json` (golden: every edge, every unresolved call),
`mixed-fullstack` with its `not_found` call, every other fixture unchanged except the version, schema accept and
reject samples for v8, and determinism (two runs byte-identical).

## 2. By hand

```
uv run graphora analyze ../fixtures/repos/http-bridge/repo --out /tmp/g.json
uv run graphora query /tmp/g.json dependents backend/app/items.py
uv run graphora query /tmp/g.json impact backend/app/items.py
```

Expected: the frontend files that call the items routes are listed with `(likely)`; edge `symbol`s read like
`GET /api/items`; `overview` counts the unresolved HTTP calls.

## 3. Verifier

A dependency claim from a frontend call line to the backend route file verifies as `heuristic` (unit test in
`tests/unit/test_verify_graph.py`).
