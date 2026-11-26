"""`POST /api/v1/ask`: the 012 agents on one stored snapshot, streamed as server-sent events
(specs/013-ask-sse/contracts/http-api.md).

The request is checked in the order body → pair → slot → snapshot load → model, and refused as a normal API
error before any stream opens. An accepted ask runs the synchronous agents in its own thread with its own store
connection; trace events cross to the event loop through an asyncio queue (research R3, R6). Closing the
connection or stopping the service sets the run's stop: no new model or tool call is made (research R5).
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import threading
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.sse import EventSourceResponse, format_sse_event
from starlette.background import BackgroundTask

from graphora.agents import ModelUnavailable, ask, model
from graphora.api.errors import ApiError, bad_request, busy, model_unavailable
from graphora.api.routes import _missing, _params
from graphora.mcp import PairNotFound, Served, from_store
from graphora.pipeline.jobs import Stopping
from graphora.store import Store

log = logging.getLogger("graphora.api")

MAX_QUESTION = 2000
KEEPALIVE_SECONDS = 15.0
_KEYS = ("question", "repository", "snapshot")
_PING = b": ping\n\n"
_numbers = itertools.count(1)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def parse_ask(body: Any) -> tuple[str, str, str]:
    """(repository, snapshot, question) from the parsed body, or a bad request (data-model.md § AskRequest)."""
    if not isinstance(body, dict):
        raise bad_request("the body must be a JSON object")
    for key in sorted(body):
        if key not in _KEYS:
            raise bad_request(f"unknown key: {key}")
    values = {}
    for key in ("repository", "snapshot", "question"):
        value = body.get(key)
        if not isinstance(value, str) or not value.strip():
            raise bad_request(f"missing {key}")
        values[key] = value
    question = values["question"].strip()
    if len(question) > MAX_QUESTION:
        raise bad_request(f"question is longer than {MAX_QUESTION} characters")
    return values["repository"], values["snapshot"], question


class AskRun:
    """One accepted ask: its own snapshot and connection, a stop event, a queue and a thread."""

    def __init__(self, service: AskService, served: Served, chat: Any, question: str, loop: asyncio.AbstractEventLoop) -> None:
        self.service = service
        self.served = served
        self.chat = chat
        self.question = question
        self.loop = loop
        self.stop = threading.Event()
        self.queue: asyncio.Queue[tuple[str, Any] | None] = asyncio.Queue()
        self.thread = threading.Thread(target=self._run, name=f"graphora-ask-{next(_numbers)}", daemon=True)
        self.state = "new"  # new → started (the thread owns cleanup) or new → closed (never started)
        self._state = threading.Lock()

    def begin(self) -> bool:
        """Start the thread unless the run was stopped or abandoned first; False when it will not run."""
        with self._state:
            if self.state != "new" or self.stop.is_set():
                start = False
            else:
                self.state = "started"
                start = True
        if not start:
            self.abandon()
            return False
        self.thread.start()
        return True

    def abandon(self) -> None:
        """Release a run whose thread never started: its connection and its slot. A no-op once started."""
        with self._state:
            if self.state != "new":
                return
            self.state = "closed"
        self.stop.set()
        AskService._close(self.served)
        self.service._finished(self)

    def _put(self, item: tuple[str, Any] | None) -> None:
        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, item)
        except RuntimeError:  # the loop is closed: nobody reads any more
            self.stop.set()

    def _run(self) -> None:
        try:
            run = ask(
                self.question,
                self.served,
                model=self.chat,
                setting=self.service.setting,
                on_event=lambda event: self._put(("step", event)),
                stop=self.stop.is_set,
            )
            self._put(("answer", run))
        except Exception as exc:
            log.error("ask failed", exc_info=exc)
            self._put(("error", None))
        finally:
            if self.served.store is not None:
                self.served.store.close()
            self.service._finished(self)
            self._put(None)

    async def stream(self) -> AsyncIterator[bytes]:
        """Steps as they happen, then one answer or error; a ping after each silence of KEEPALIVE_SECONDS. The
        thread starts here, so a request dropped before the stream starts never runs the agents."""
        try:
            if not self.begin():
                return
            while True:
                try:
                    item = await asyncio.wait_for(self.queue.get(), KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield _PING
                    continue
                if item is None:
                    return
                kind, value = item
                if kind == "step":
                    yield format_sse_event(event="step", id=str(value.n), data_str=_json(value.to_dict()))
                elif kind == "answer":
                    yield format_sse_event(event="answer", data_str=_json(value.to_dict()))
                else:
                    yield format_sse_event(event="error", data_str=_json({"message": "internal error"}))
        finally:
            self.stop.set()


class AskService:
    """The asks of one `graphora serve`: at most `limit` at once, separate from analysis jobs (research R4)."""

    def __init__(
        self,
        store: Store,
        url: str,
        setting: str | None = None,
        limit: int = 1,
        model_factory: Callable[[str], Any] | None = None,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self.store = store
        self.url = url
        self.setting = setting or model.setting_from_env()
        self.limit = limit
        self.model_factory = model_factory
        self._slots = threading.BoundedSemaphore(limit)
        self._lock = threading.Lock()
        self._runs: set[AskRun] = set()
        self._stopping = False

    def _build(self) -> Any:
        factory = self.model_factory or model.model_from_setting
        return factory(self.setting)

    def open(self, repository: str, snapshot: str, question: str, loop: asyncio.AbstractEventLoop) -> AskRun:
        """Check, take a slot, load the snapshot, build the model and start the run; ApiError before any work."""
        if self._stopping:
            raise Stopping()
        if not self.store.has_snapshot(repository, snapshot):
            raise _missing(self.store, repository, snapshot)
        if not self._slots.acquire(blocking=False):
            raise busy()
        served = None
        try:
            served = from_store(self.url, repository, snapshot)
            chat = self._build()
        except PairNotFound as exc:
            self._slots.release()
            raise ApiError("not_found", 404, exc.message) from None
        except ModelUnavailable as exc:
            self._close(served)
            self._slots.release()
            raise model_unavailable(exc.message) from None
        except BaseException:
            self._close(served)
            self._slots.release()
            raise
        run = AskRun(self, served, chat, question, loop)
        with self._lock:
            if self._stopping:
                self._close(served)
                self._slots.release()
                raise Stopping()
            self._runs.add(run)
        return run

    @staticmethod
    def _close(served: Served | None) -> None:
        if served is not None and served.store is not None:
            served.store.close()

    def _finished(self, run: AskRun) -> None:
        with self._lock:
            if run in self._runs:
                self._runs.discard(run)
                self._slots.release()

    def running(self) -> int:
        with self._lock:
            return len(self._runs)

    def stop(self, timeout: float = 120.0) -> None:
        """Refuse new asks, stop every run and wait for them, within `timeout` seconds in total."""
        with self._lock:
            self._stopping = True
            runs = list(self._runs)
        for run in runs:
            run.stop.set()
            run.abandon()  # a run whose stream never started
        deadline = time.monotonic() + timeout
        for run in runs:
            if run.thread.ident is not None:  # a run added by open() whose thread is not started yet
                run.thread.join(max(0.0, deadline - time.monotonic()))


def router(service: AskService) -> APIRouter:
    api = APIRouter(prefix="/api/v1")

    @api.post("/ask")
    async def ask_question(request: Request) -> EventSourceResponse:
        _params(request, ())
        try:
            body = json.loads(await request.body())
        except (ValueError, UnicodeDecodeError):
            raise bad_request("the body must be a JSON object") from None
        repository, snapshot, question = parse_ask(body)
        run = await run_in_threadpool(service.open, repository, snapshot, question, asyncio.get_running_loop())
        # runs after the response, also when the client left before the stream started (research R5)
        return EventSourceResponse(run.stream(), background=BackgroundTask(run.abandon))

    return api
