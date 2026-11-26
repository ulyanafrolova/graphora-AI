# Quickstart: Agents

Validation guide for 012. Contracts: [agents.md](contracts/agents.md), [cli.md](contracts/cli.md).

## Prerequisites

```
cd backend && uv sync
make db
export GRAPHORA_TEST_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora_test
export GRAPHORA_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora
```

For the live checks only: Ollama running natively, `ollama pull qwen3:8b`.

## 1. Scripted tests (no model, CI)

```
uv run pytest -m "not llm and not slow" -k agents
```

Expected: all pass. They cover, with scripted model replies on stored fixtures:

- `py-cycles` "what breaks if I change …": every direct dependent from `expected.json` is a fact; every fact
  re-verifies (US1, SC-001, SC-005).
- `mixed-fullstack` "will the frontend break if I change the backend API?": the claim
  `frontend/src/api.ts → backend/app/api.py` is rejected `no_edge`, revised twice, ends as a hypothesis
  (US2, SC-004).
- `py-flat` wrong line then corrected line: the second round's claim is a fact and closes the hypothesis.
- Unknown tool, broken arguments, endless tool calls, text-only replies, a model error: each run ends within
  15 tool calls and 2 revisions with the right end reason (US3, SC-003).
- Two runs with the same script give byte-identical `Run` JSON (SC-006).
- A model summary naming an unproven file is replaced by the code summary (FR-014).

## 2. Command line with a graph file

```
uv run graphora analyze ../fixtures/repos/py-cycles/repo --out /tmp/g.json
uv run graphora ask "What breaks if I change loop/a.py?" --graph /tmp/g.json --trace -
```

Expected: `Facts`, `Likely`, `Hypotheses (not proven)` and `Summary` parts; every fact line ends with
`path:line@snapshot`; trace lines on stderr; exit 0. (`loop/a.py` is part of the fixture's import cycle.)

## 3. Unreachable model

```
OLLAMA_HOST=http://127.0.0.1:1 uv run graphora ask "What imports loop/a.py?" --graph /tmp/g.json; echo $?
```

Expected: one `graphora: error: model ollama:qwen3:8b unavailable at http://127.0.0.1:1: cannot connect` line, no traceback, `9`.

## 4. Live model (manual, SC-007)

```
GRAPHORA_TEST_MODEL=ollama:qwen3:8b uv run pytest -m llm -k agents
time uv run graphora ask "What breaks if I change backend/app/models.py?" --repository mixed-fullstack --snapshot <id>
```

Expected: under 2 minutes on a developer laptop; the test asserts the budget held and every fact verifies.
Wording is not checked.
