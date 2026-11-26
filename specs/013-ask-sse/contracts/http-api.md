# Contract: `POST /api/v1/ask`

Runs the 012 agents on one stored snapshot and streams the trace as server-sent events. Part of `graphora
serve` (005, 010). Types: [data-model.md](../data-model.md).

## Request

```
POST /api/v1/ask
Content-Type: application/json

{"repository": "py-cycles", "snapshot": "content:485322f43c0d7bd4", "question": "What breaks if I change loop/a.py?"}
```

No query parameters (any → `400 unknown parameter: <k>`).

## Refusals (normal JSON error, no stream)

Body `{"error": {"kind": "...", "message": "..."}}` as the rest of the API.

| Status | `kind` | When / message |
|---|---|---|
| 400 | `bad_request` | `the body must be a JSON object`, `unknown key: <k>`, `missing repository` / `missing snapshot` / `missing question` (absent, not a string or empty), `question is longer than 2000 characters` |
| 404 | `not_found` | `repository not found: <r>`, `snapshot not found: <r> <s>` |
| 429 | `busy` | `another question is being answered; try again later`, header `Retry-After: 30` |
| 503 | `model_unavailable` | the 012 `ModelUnavailable` message, e.g. `model nope:x unavailable at the nope API: Unsupported provider='nope'.` |
| 503 | `store_unavailable` | `store unavailable` |
| 503 | `stopping` | `the service is stopping` (after shutdown began) |

Checks run in this order: body, pair (a cheap lookup in the shared store), slot, then the run's own snapshot
load and the model; a refused request loads no graph, takes no slot and calls no model.

## Stream (`200`, `Content-Type: text/event-stream`)

```
event: step
id: 1
data: {"detail":"round 0","kind":"role_start","n":1,"role":"explorer"}

event: step
id: 2
data: {"args":{"target":"loop/a.py"},"citation_ids":["c1","c2"],"cut":false,"kind":"tool_call","n":2,"role":"explorer","tool":"dependents"}

: ping

…

event: answer
data: {"answer":{…},"trace":[…]}
```

- One `step` per trace event, in order, `id` = `n` (1, 2, 3, …), sent as it happens.
- Exactly one last message: `answer` (`Run.to_dict()`, the content of `graphora ask --json`; `end` may be any
  012 end reason or `stopped`; `error` present when the model failed) or `error`
  (`{"message": "internal error"}`). Then the response ends.
- `: ping` comment after every 15 s without a message.
- `step` data never contains file content or model text.

## Disconnect and shutdown

- Closing the connection stops the run before its next model or tool call; the slot is freed when the run
  stops (after at most the model call in progress).
- On `graphora serve` shutdown, open streams are closed after 5 s and their runs stopped the same way.

## `graphora serve` options (new)

| Option | Default | Meaning |
|---|---|---|
| `--asks N` | 1 | questions answered at the same time (≥ 1) |
| `--model PROVIDER:MODEL` | `$GRAPHORA_MODEL` or `ollama:qwen3:8b` | the agents' model |

## Example

```
curl -N -X POST localhost:8000/api/v1/ask -H 'Content-Type: application/json' \
  -d '{"repository":"py-cycles","snapshot":"<id>","question":"What breaks if I change loop/a.py?"}'
```
