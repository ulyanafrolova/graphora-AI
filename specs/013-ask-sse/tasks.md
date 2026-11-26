---

description: "Task list for 013-ask-sse"
---

# Tasks: Ask over HTTP with a Streamed Trace

**Input**: Design documents from `specs/013-ask-sse/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R9), data-model.md, contracts/http-api.md, quickstart.md

**Tests**: Required (spec FR-015, constitution VIII). Within each phase, write the tests first and confirm they
fail. Tests use the 012 `ScriptedModel` (`backend/tests/unit/scripted_model.py`); no live model in CI.

**Organization**: Phase 2 (012 stop signal, `AskService` skeleton, body parsing, app wiring, test helpers)
blocks every story. Then:

- US1 (P1): the stream of steps and the final answer;
- US2 (P1): refusals before any work;
- US3 (P2): ask slots, separate from analysis jobs;
- US4 (P2): disconnect and shutdown stop the run;
- US5 (P3): keep-alive during silences.

Paths are relative to the repository root. Code lives in `backend/src/graphora/`, tests in `backend/tests/`.
Run commands from `backend/`. Keep comments minimal, in the style of `api/jobs.py` (module docstring with a
spec reference, one-line docstrings only where not obvious). Store-backed tests are marked `db` and use the
`store` / `database_url` fixtures and `analyze_fixture` from `tests/conftest.py`.

**Commits** (one per milestone, pushed right after): `tasks: 013 ask over http` for this file; then
`ask: stop signal, service and stream` (Phases 1–4), `ask: slots, disconnect and keep-alive` (Phases 5–7),
and a final pass `ask: docs and checks` (Phase 8).

## Phase 1: Setup

- [X] T001 Write `backend/tests/integration/sse.py`: `read_stream(response) -> list[tuple[str, str | None,
  str]]` parsing a `text/event-stream` body into `(event, id, data)` messages and keep-alive comments as
  `("ping", None, "")`; `messages(...)` drops pings; `data` is the raw `data:` line. One-line module docstring
  referencing `specs/013-ask-sse`.

---

## Phase 2: Foundational

**Purpose**: what every story needs (research R1, R3, R4, R5; data-model.md).

### Tests

- [X] T002 [P] Write `backend/tests/unit/test_agents_stop.py` (no store, `tests/unit/agent_world.py`):
  `ask(..., stop=lambda: True)` makes no model call and ends `stopped` with an empty answer; a stop that turns
  true after the first `tool_call` event (set from `on_event`) lets the current tool call finish, makes no
  further model or tool call (script has unused replies left) and ends `stopped`, keeping facts verified
  before; a stop set during the analyst's tool loop still makes no claims call; `end_reason` puts `stopped`
  before `model_failed`; without `stop` every 012 test still passes (run `tests/unit/test_agents_*.py`).
- [X] T003 [P] Write `backend/tests/unit/test_api_ask_body.py`: `parse_ask(body)` per data-model.md §
  AskRequest — returns `(repository, snapshot, question)` with the question trimmed; refuses with `ApiError`
  kind `bad_request` and the exact messages of contracts/http-api.md: `the body must be a JSON object` (list,
  string, invalid JSON bytes), `unknown key: <k>`, `missing repository` / `missing snapshot` / `missing
  question` (absent, not a string, empty or blank), `question is longer than 2000 characters` (2,001 after
  trimming; 2,000 is accepted).

### Implementation

- [X] T004 Add the stop signal to the 012 agents: `stop: Callable[[], bool] | None = None` keyword on `ask` in
  `backend/src/graphora/agents/graph.py`, checked before every model call (`_call`) and every tool call (tool
  loop), setting `failed = "stopped"` and making no new call; add `"stopped"` to `EndReason` / `END_REASONS`
  in `backend/src/graphora/agents/state.py`; `end_reason` in `backend/src/graphora/agents/review.py` returns
  `stopped` first. Update `specs/012-agents/contracts/agents.md` (the `ask` signature and the end reasons) and
  `specs/012-agents/data-model.md` § EndReason.
- [X] T005 Create `backend/src/graphora/api/ask.py`: module docstring referencing
  `specs/013-ask-sse/contracts/http-api.md`; `MAX_QUESTION = 2000`; `parse_ask(body)`;
  `AskService(url, setting, limit=1, model_factory=model_from_setting)` with `setting` defaulting to
  `setting_from_env()` and a `threading.BoundedSemaphore(limit)` slot counter (open/stop come in US1–US4);
  `router(service) -> APIRouter` with prefix `/api/v1` (empty for now).
- [X] T006 Add `ApiError` helpers to `backend/src/graphora/api/errors.py`: `busy()` (kind `busy`, 429, message
  `another question is being answered; try again later`) and `model_unavailable(message)` (kind
  `model_unavailable`, 503); make `_api_error` add `Retry-After: 30` for kind `busy`.
- [X] T007 Extend `create_app(store, runner=None, asks=None)` in `backend/src/graphora/api/__init__.py` to
  include `ask.router(asks)` when given; add an `ask_app` fixture to `backend/tests/conftest.py`: stores the
  `py-cycles` fixture, builds `AskService(database_url, "scripted:test", model_factory=...)` whose factory
  returns the next `ScriptedModel` from a list the test sets, and yields `(TestClient, service, snapshot,
  scripts)`; `indirect` parameters override `limit`.
- [X] T008 Run `uv run pytest tests/unit/test_agents_stop.py tests/unit/test_api_ask_body.py
  tests/unit/test_agents_*.py` until green.

---

## Phase 3: User Story 1 - Ask a question and watch the agents work (P1) 🎯 MVP

**Goal**: `POST /api/v1/ask` streams one `step` per trace event as it happens and ends with one `answer`.

**Independent Test**: stored `py-cycles`, scripted model; the stream's steps equal the trace of a direct
`ask` with the same script, and the `answer` equals `graphora ask --json`.

### Tests

- [X] T009 [US1] Write `backend/tests/integration/test_api_ask.py` (marked `db`, uses `ask_app` and
  `tests/integration/sse.py`): (a) the 012 "what breaks" script on `py-cycles` → response 200
  `text/event-stream`; messages are `step` with ids `1…N` in order, then exactly one `answer`; the parsed step
  data equal `[e.to_dict() for e in run.trace]` of a direct `ask` with an identical script on the same stored
  snapshot; the parsed `answer` equals the JSON printed by `graphora ask --json` with an identical script
  (run through `graphora.cli.main` with `model_from_setting` patched, store mode) (SC-002); (b) a script whose
  claim is rejected → `verdict`, `hypothesis` and `revision` steps come before `answer`, and the claim is only
  in `answer.hypotheses`; (c) a script raising `httpx.ConnectError` after one tool call → last message
  `answer` with `answer.end == "model_failed"`, `error` set, earlier facts kept; (d) an exception that is not a
  model failure (patch `graphora.api.ask.ask` to raise `RuntimeError`) → last message `error` with
  `{"message": "internal error"}` and no traceback text; (e) no `step` data contains a line of a fixture file,
  any scripted model text or the question text (the question appears only in `answer.question`); (f) the first `step` is received before the scripted model's first reply is
  released (reply gated on a `threading.Event` set after the first step is read), within 1 s of sending the
  request (SC-001).

### Implementation

- [X] T010 [US1] Implement `AskRun` in `backend/src/graphora/api/ask.py` (data-model.md § AskRun): its own
  `Served`, the model, a `threading.Event` stop, an `asyncio.Queue` and a daemon thread
  `graphora-ask-<n>` running 012 `ask(question, served, model=…, setting=…, on_event=…, stop=stop.is_set)`;
  `on_event` and the end hand messages to the loop with `loop.call_soon_threadsafe`; the thread's `finally`
  closes `served.store`, releases the slot and puts the end marker; any non-model exception is logged with
  `log.error(..., exc_info=…)` and sent as `error`.
- [X] T011 [US1] Implement `AskService.open(repository, snapshot, question)` (check the pair with the shared
  store's `has_snapshot`/`has_repository`, take a slot, then load the run's own `Served` with `from_store`,
  build the model, start the run; `AskService` gets the shared `Store` for the cheap check) and the endpoint `POST /ask` in `router` with
  `response_class=EventSourceResponse`: parse the body (`_params(request, ())` first, like `/jobs`), call
  `open` in the thread pool, then an async generator yielding `ServerSentEvent(event="step", id=str(n),
  raw_data=…)`, `ServerSentEvent(event="answer", raw_data=…)` or `ServerSentEvent(event="error",
  raw_data=…)`, with compact sorted-key JSON (`json.dumps(…, sort_keys=True, ensure_ascii=False,
  separators=(",", ":"))`).
- [X] T012 [US1] Run `uv run pytest tests/integration/test_api_ask.py` until green.

---

## Phase 4: User Story 2 - Bad requests are refused before any work starts (P1)

**Goal**: every refusal of contracts/http-api.md § Refusals, in the order body → pair → slot → model, with no
model call and no slot taken.

**Independent Test**: each bad request gets its status and message; the model factory is never called.

### Tests

- [X] T013 [US2] Extend `backend/tests/integration/test_api_ask.py`: unknown repository → 404
  `repository not found: nope`; unknown snapshot → 404 `snapshot not found: py-cycles nope`; each bad body of
  T003 → 400 with its message; a query parameter → 400 `unknown parameter: x`; a model factory raising
  `ModelUnavailable` → 503 `model_unavailable` with its message; in every case the response is JSON (not a
  stream), the factory call count is 0 (except the 503 case, 1), `from_store` is not called for not-found and
  busy refusals (spy on `graphora.api.ask.from_store`), no slot is held afterwards
  (`service` accepts the next ask), and the answer arrives within 1 s (SC-003).

### Implementation

- [X] T014 [US2] Complete the checks in `AskService.open` and the endpoint in
  `backend/src/graphora/api/ask.py`, in the order body → pair (shared store lookup, `not_found` with the
  `GET /api/v1/graph` messages) → slot (`acquire(blocking=False)`, → `busy()`) → `from_store` load
  (`PairNotFound` after a race → `not_found`, releasing the slot) → model; `StoreUnavailable` passes to the
  existing handler; a refused request never calls `from_store`; build the model last (`ModelUnavailable` → `model_unavailable(exc.message)`, releasing the slot and closing the store);
  the model is never invoked before the stream starts.
- [X] T015 [US2] Run `uv run pytest tests/integration/test_api_ask.py` until green.

**Checkpoint**: commit `ask: stop signal, service and stream` and push.

---

## Phase 5: User Story 3 - The local model is shared fairly (P2)

**Goal**: at most `--asks` runs at once, extra asks refused as `busy`, jobs unaffected.

**Independent Test**: one gated ask open, a second refused 429 with `Retry-After: 30`, an analysis job
completes meanwhile.

### Tests

- [X] T016 [P] [US3] Write `backend/tests/integration/test_api_ask_slots.py` (marked `db`): with a scripted
  model gated on a `threading.Event`, (a) a second ask while the first waits → 429 `busy`, header
  `Retry-After: 30`, no second model built; (b) after the first stream ends, an ask is accepted; (c) with
  `limit=2` two gated asks are accepted and the third is busy; (d) with the app built with both a `JobRunner`
  (as `job_app`) and `AskService`, a ZIP job submitted while a gated ask waits reaches `done` (SC-005);
  (e) while a gated ask waits, `GET /api/v1/graph` and `GET /api/v1/file` for the same snapshot answer 200
  within 1 s (FR-014).

### Implementation

- [X] T017 [US3] Add `--asks N` (default 1, ≥ 1, error `--asks must be at least 1`) and `--model` to `serve` in
  `backend/src/graphora/cli/__init__.py`; build `AskService(url, args.model or setting_from_env(),
  limit=args.asks)` and pass it to `create_app(store, runner, service)`.
- [X] T018 [US3] Run `uv run pytest tests/integration/test_api_ask_slots.py tests/integration/test_serve_jobs_cli.py`
  until green; add a case to the serve CLI tests that `--asks 0` exits 2.

---

## Phase 6: User Story 4 - A client that goes away stops the work (P2)

**Goal**: a disconnect or shutdown sets the run's stop; no new model or tool call; slot and connection freed
when the run ends.

**Independent Test**: close the stream after the first step with a gated scripted model; after releasing the
gate, the script has unused replies, the run ended `stopped`, the slot is free.

### Tests

- [X] T019 [US4] Extend `backend/tests/integration/test_api_ask_slots.py`: (a) read the first `step`, close
  the `TestClient` stream, release the gate → within 2 s the run's thread has ended, `stop` is set, the
  scripted model has unused replies left (no new call), the store connection is closed and a new ask is
  accepted (SC-004); the suite's network block (`tests/conftest.py` `_no_network`) stays on, so a run reaching any
  address other than the scripted model fails the test (FR-013); (b) calling `aclose()` on the endpoint's async generator directly (unit-level) sets the
  stop event; (c) `AskService.stop()` with a gated run sets its stop, releases the gate's waiter within one
  call and joins the thread; nothing is written to the store (row counts of `analyses` and `files` unchanged).

### Implementation

- [X] T020 [US4] In `backend/src/graphora/api/ask.py`: the async generator sets `run.stop` in `finally`
  (disconnect, cancellation, normal end); `AskService.stop()` sets every running stop and joins all threads
  within one overall limit of 120 s (daemon threads left after it end with the process); the service refuses new asks after `stop()` with the existing `Stopping` error.
- [X] T021 [US4] In `_serve` in `backend/src/graphora/cli/__init__.py`: run uvicorn with
  `timeout_graceful_shutdown=5`; after `uvicorn.run` returns, call `asks.stop()` (refuse new asks, set every
  stop, join all run threads within one overall limit of 120 s) and then `runner.stop()`, in the `finally`.
- [X] T022 [US4] Run `uv run pytest tests/integration/test_api_ask_slots.py` until green.

---

## Phase 7: User Story 5 - Long silences do not break the connection (P3)

**Goal**: `: ping` after each 15 s of silence, not a step.

**Independent Test**: with the keep-alive interval patched to 0.2 s and a gated model, pings arrive while
waiting and step ids stay consecutive.

### Tests

- [X] T023 [US5] Extend `backend/tests/integration/test_api_ask_slots.py`: monkeypatch
  `fastapi.sse._PING_INTERVAL` (and the name FastAPI's routing module imported, if any) to `0.2`; hold the
  gate for 1 s → at least 3 `ping` entries before the next `step`; `messages(...)` without pings has step ids
  `1…N` consecutive and ends with `answer` (SC-006); assert the unpatched value is `15.0` (FR-007).

### Implementation

- [X] T024 [US5] No code beyond `EventSourceResponse`; if T023 shows FastAPI's interval cannot be patched in
  tests, wrap the generator to yield a comment `ServerSentEvent(comment="ping")` after
  `KEEPALIVE_SECONDS = 15` of queue silence in `backend/src/graphora/api/ask.py` instead. Run the test until
  green and record which way was taken in `specs/013-ask-sse/research.md` § R2.

**Checkpoint**: commit `ask: slots, disconnect and keep-alive` and push.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T025 [P] Update `CLAUDE.md` § Commands with `serve --asks/--model` and the `curl -N -X POST
  localhost:8000/api/v1/ask …` example; in `docs/product/project-context.md` §5 replace `POST
  /repos/{id}/ask … planned, feature 013` with `POST /api/v1/ask  question to agents, streamed (SSE): 013`.
- [ ] T026 Run `make db` and `make check` (ruff and the full suite with PostgreSQL); fix findings.
- [ ] T027 Run quickstart sections 2–3 (`specs/013-ask-sse/quickstart.md`) against a live Ollama model; note
  the time to the first `step` and to the `answer`, and the busy/disconnect behaviour, in the PR description.

**Checkpoint**: commit `ask: docs and checks` and push.

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → US1 → US2 → US3 → US4 → US5 → Polish.
- US2 refines `AskService.open` from US1; US3 adds the serve options; US4 needs the stop signal (T004) and the
  stream (T011); US5 needs only the stream.
- Within Phase 2: T002 and T003 in parallel; T004 before T005–T007 (the service passes `stop`).

## Parallel Examples

- Phase 2 tests: T002, T003.
- US3 test T016 can be written while US2 is implemented (different file).
- Polish: T025 alongside T026.

## Implementation Strategy

- **MVP**: Phases 1–3 (US1): a stored snapshot answered over HTTP with live steps and the CLI-equal answer.
- Then US2 (clear refusals), US3 (one model, one ask), US4 (closed tab frees the model), US5 (keep-alive).
- Each checkpoint leaves the suite green.
