# Data Model: Ask over HTTP

No stored data. Types in `graphora/api/ask.py`; the 012 types (`Run`, `Answer`, `TraceEvent`) are reused.
Research: [research.md](research.md).

## AskRequest (parsed body)

| Field | Type | Rule |
|---|---|---|
| `repository` | str | non-empty |
| `snapshot` | str | non-empty |
| `question` | str | trimmed; 1–2,000 characters |

Any other key → `unknown key: <k>`; body not a JSON object → `the body must be a JSON object`.

## AskService (one per `graphora serve`)

| Field | Rule |
|---|---|
| `url` | database URL of the service |
| `setting` | model setting: `--model`, else `$GRAPHORA_MODEL`, else `ollama:qwen3:8b` |
| `limit` | `--asks`, ≥ 1, default 1 |
| `model_factory` | `model_from_setting` (tests pass a scripted model factory) |
| running | set of `AskRun`s; `len ≤ limit` |

Operations: `open(request) -> AskRun` (validate pair, take a slot, build the model; raises `ApiError`
400/404/429/503 before any stream), `stop()` (stop every run, join threads).

## AskRun (one per accepted request)

| Field | Rule |
|---|---|
| `served` | its own `Served` from `from_store` (own store connection) |
| `model` | built from the setting |
| `stop` | `threading.Event`; set on disconnect, shutdown |
| `queue` | `asyncio.Queue` of `Message`; filled from the agent thread with `call_soon_threadsafe` |
| `thread` | daemon thread running 012 `ask(..., on_event=…, stop=stop.is_set)` |

Lifecycle:

```
accepted ──thread starts──▶ running ──ask returns──▶ answered (queue: answer, end)
   │                           │──exception──▶ failed (queue: error, end)
   │                           └──stop set──▶ stopping ──ask returns (end = stopped)──▶ answered
   └─ slot taken                                     slot released + store closed when the thread ends
```

## Message (server-sent event)

| `event` | `id` | `data` |
|---|---|---|
| `step` | `str(n)` | `TraceEvent.to_dict()` |
| `answer` | — | `Run.to_dict()` (`answer`, `trace`, `error` when set) |
| `error` | — | `{"message": "internal error"}` |
| keep-alive | — | comment line `: ping` (no event, no data) |

`data` is compact JSON with sorted keys on one line.

## 012 changes

- `ask(..., stop: Callable[[], bool] | None = None)`: checked before each model and tool call.
- `EndReason` gains `stopped`, first in the order: `stopped` > `model_failed` > `model_budget_spent` >
  `budget_spent` > `revisions_spent` > `no_claims` > `answered`.
