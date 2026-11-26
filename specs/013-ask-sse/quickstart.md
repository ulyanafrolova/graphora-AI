# Quickstart: Ask over HTTP

Validation guide for 013. Contract: [contracts/http-api.md](contracts/http-api.md).

## Prerequisites

```
cd backend && uv sync
make db
export GRAPHORA_TEST_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora_test
export GRAPHORA_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora
```

For the live check only: Ollama running natively with a pulled model.

## 1. Tests (scripted model, CI)

```
uv run pytest -k ask -m "not llm"
```

Expected: all pass. They cover:

- the stream for a stored `py-cycles` question: `step` ids 1…N in order, equal to a direct 012 `ask` trace;
  last message `answer` equal to `graphora ask --json` for the same script (US1, SC-002);
- refusals: unknown repository/snapshot (404), bad bodies (400), model setting unusable (503), all with no
  model call (US2, SC-003);
- busy: a second ask while one waits → 429 with `Retry-After`; an analysis job still runs (US3, SC-005);
- disconnect: closing the stream sets the stop, no further model call, the slot is free again, end `stopped`
  (US4, SC-004);
- keep-alive with a shortened interval: `: ping` lines during a wait, not counted as steps (US5, SC-006).

## 2. Live service

```
uv run graphora analyze ../fixtures/repos/py-cycles/repo --store
uv run graphora serve --model ollama:qwen3:4b &
curl -s localhost:8000/api/v1/repositories                    # take the snapshot id
curl -N -X POST localhost:8000/api/v1/ask -H 'Content-Type: application/json' \
  -d '{"repository":"repo","snapshot":"<id>","question":"What breaks if I change loop/a.py?"}'
```

Expected: `event: step` lines start within a second; `: ping` lines during long model calls; the stream ends
with `event: answer` whose `answer.facts` cite `loop/c.py:1` and `user.py:1`. (The repository name is the one
`analyze --store` printed.)

## 3. Busy and disconnect by hand

While the stream of section 2 runs, send the same `curl` in a second terminal: expect `429` and
`{"error":{"kind":"busy",…}}`. Press Ctrl-C on the first `curl`: within one model call a new ask is accepted.
