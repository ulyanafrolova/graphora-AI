# Research: Ask over HTTP with a Streamed Trace

Decisions for [spec.md](spec.md). Each one: decision, rationale, alternatives considered.

## R1. Route and request

**Decision**: `POST /api/v1/ask` with a JSON body `{"repository": "...", "snapshot": "...", "question": "..."}`,
no query parameters. Body parsing follows `POST /api/v1/jobs`: the body must be a JSON object, unknown keys are
a bad request (`unknown key: <k>`), each field must be a non-empty string (`missing repository`, …), the
question is trimmed and at most 2,000 characters (`question is longer than 2000 characters`).

**Rationale**: the existing API names snapshots by `repository` and `snapshot`; there is no repository id
(`/repos/{id}`) anywhere. A body (not query parameters) keeps a long question out of URLs and access logs.

**Alternatives**: `POST /repos/{id}/ask` from the product context — rejected, no such id exists; `GET` with
query parameters (for the browser `EventSource` API) — rejected: `EventSource` cannot send a body and puts the
question in the URL; the UI reads the stream with `fetch` instead (works with `POST`).

## R2. Streaming with FastAPI's server-sent events

**Decision**: the endpoint returns FastAPI's built-in `EventSourceResponse` (FastAPI 0.162, `fastapi.sse`) from
an async generator yielding `ServerSentEvent`s:

| `event` | `id` | `data` (`raw_data`, compact JSON with sorted keys) |
|---|---|---|
| `step` | trace event `n` | `TraceEvent.to_dict()` |
| `answer` | — | `Run.to_dict()`: the same document as `graphora ask --json` |
| `error` | — | `{"message": "<short reason>"}` |

FastAPI inserts the keep-alive comment `: ping` after 15 s without an item (`fastapi.sse._PING_INTERVAL`), which
is FR-007; tests shorten it by monkeypatching that constant, as its docstring allows.

**Rationale**: no new dependency; the keep-alive, the `text/event-stream` media type and the event encoding
already exist and are tested upstream. `raw_data` with our own `json.dumps(sort_keys=True)` keeps the bytes
deterministic, like the other API bodies.

**Alternatives**: `sse-starlette` — rejected, a new dependency for what FastAPI now ships; a plain
`StreamingResponse` with hand-written framing — rejected, re-implements keep-alive; WebSockets — rejected,
one-way streaming is all that is needed and SSE passes through proxies as plain HTTP.

## R3. Running the agents next to the event loop

**Decision**: the agents run in a dedicated daemon `threading.Thread` per ask (they are synchronous: LangGraph
`invoke`, a blocking model client, psycopg). The thread passes `on_event` that hands each event to the request's
`asyncio.Queue` with `loop.call_soon_threadsafe`; when `ask` returns it hands over the final `Run` (or an
internal error) the same way and closes the queue. The async generator awaits the queue and yields events.

**Rationale**: the event loop never blocks; events are sent the moment they happen (FR-005); the async
generator's `await queue.get()` is cancellable, which is how a disconnect reaches us (R5). A thread of our own
(not `anyio.to_thread`) is not part of a limited pool and can be told to stop and joined at shutdown.

**Alternatives**: `anyio.to_thread.run_sync` — rejected: shares the default 40-thread limiter with every
synchronous endpoint and cannot be joined; making the agents async — rejected, out of scope and the store is
synchronous.

## R4. Ask slots and the model setting

**Decision**: an `AskService` created by `graphora serve` holds the database URL, the model setting
(`--model` or `GRAPHORA_MODEL`, default `ollama:qwen3:8b`), and a non-blocking slot counter (`--asks`, default
1). A request takes a slot with `acquire(blocking=False)` after validation; failing that it is refused with
429 `busy`, the message "another question is being answered; try again later" and `Retry-After: 30`. The slot
is released by the agent thread when the run ends (not by the request), so a disconnected run holds its slot
until it really stops (FR-011). Analysis jobs keep their own `JobRunner` workers; nothing is shared (FR-010).

The model object is built per request with 012 `model_from_setting` (cheap, no connection). An unusable
setting is refused with 503 `model_unavailable` and the `ModelUnavailable` message (FR-003).

**Rationale**: one local model serves one answer at a time well; a busy refusal is visible in the UI, a queue
is not. Building the model per request lets `serve` start and serve graphs even when the model setting is wrong.

**Alternatives**: a queue of waiting asks — rejected in the spec (hidden waits); running asks on the job
workers — rejected: an ask would wait behind a 5-minute analysis and vice versa.

## R5. Disconnect and shutdown stop the run

**Decision**: 012 `ask` gets one new keyword, `stop: Callable[[], bool] | None = None`. The agents check it
before every model call and every tool call (tool loops, claims call, summary call). When it returns true the
run makes no new call, goes to the answer with end reason `stopped`, which wins over every other reason. The
HTTP side sets a `threading.Event` in the generator's `finally` (reached on disconnect, when Starlette cancels
the streaming task) and on service shutdown. Without `stop`, 012 behaviour is unchanged.

Shutdown: `graphora serve` passes `timeout_graceful_shutdown=5` to uvicorn so open streams are cancelled 5 s
after Ctrl-C; their `finally` sets the stop events; `AskService.stop()` sets any left and joins the threads for
at most the time of one model call before the job runner stops. A stream cancelled this way ends without a final
answer (the connection is being closed); the spec's shutdown edge case is worded accordingly.

**Rationale**: SC-004 (at most the running model call completes); a model call cannot be interrupted safely
mid-request, a check between steps can.

**Alternatives**: killing the thread — impossible in Python; cancelling the HTTP request to Ollama — not exposed
by the LangChain client; polling `request.is_disconnected()` — needs a loop beside the queue and adds nothing
over cancellation.

## R6. Store connections

**Decision**: the request validates the pair with 012/006 `from_store(url, repository, snapshot)` in the thread
pool (it opens a new `Store`, loads and indexes the graph, and raises `PairNotFound` with exactly the API's
messages "repository not found: …" / "snapshot not found: … …"). That `Served` and its connection belong to the
ask and are closed by the agent thread when the run ends (FR-014). `StoreUnavailable` maps to the existing 503.

**Rationale**: the shared `Store` serializes access to one connection; a run doing dozens of `get_file` calls
over minutes must not hold it. Loading before the stream opens keeps not-found a normal error (FR-002).

## R7. Errors inside the run

**Decision**: model failures are already handled by 012 (`end = model_failed`, `Run.error`) and arrive as a
normal `answer`. Any other exception in the thread is logged with its traceback on the server and sent as one
`error` event `{"message": "internal error"}`; the slot and connection are released.

## R8. Testing

**Decision**: tests build the app with `create_app(store, runner=None, asks=AskService(...))` and a
`model_factory` hook on `AskService` that returns a `ScriptedModel` (012 `tests/unit/scripted_model.py`),
so no model is contacted. Streams are read with FastAPI's `TestClient` (`client.stream("POST", …)`), and the
`data:` lines parsed. Busy and disconnect tests use a scripted model whose reply waits on a `threading.Event`.
Disconnect is tested both by closing the async generator (unit) and by closing a `TestClient` stream early
(integration), asserting the stop event is set, no further model call happens, and the slot is free. All
store-backed tests are marked `db`.

## R9. Documentation

**Decision**: the HTTP contract goes to `specs/013-ask-sse/contracts/http-api.md`; `CLAUDE.md` gets the curl
example; `docs/product/project-context.md` §5 replaces `POST /repos/{id}/ask` with `POST /api/v1/ask`.
