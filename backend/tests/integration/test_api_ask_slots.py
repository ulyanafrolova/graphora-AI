"""Ask slots, disconnect, shutdown and keep-alive (specs/013-ask-sse US3–US5, SC-004–SC-006, FR-010, FR-014,
tasks T016, T019, T023). Scripted model with gated replies, stored `py-cycles`."""

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import graphora.api.ask as ask_module
from graphora.agents.claims import ClaimItem, ClaimsReply
from graphora.api import create_app
from graphora.pipeline import PipelineLimits
from graphora.pipeline.jobs import JobRunner
from jobs_helpers import fixture_zip, wait_for_job
from sse import messages, read_stream

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from scripted_model import Gated, call, scripted  # noqa: E402

pytestmark = pytest.mark.db


def gated_model():
    """A model whose second reply waits for the gate; returns (model, script, gated)."""
    gated = Gated("explorer done")
    model, script = scripted(
        call("dependents", target="loop/a.py"),
        gated,
        "no tools",
        ClaimsReply(claims=[ClaimItem(cite="c1")]),
        "Changing loop/a.py breaks loop/c.py.",
    )
    return model, script, gated


class Background:
    """A streaming request read in a thread; `lines` fill as they arrive."""

    def __init__(self, client, body):
        self.lines: list[str] = []
        self.status = None
        self.thread = threading.Thread(target=self._read, args=(client, body), daemon=True)
        self.thread.start()

    def _read(self, client, body):
        with client.stream("POST", "/api/v1/ask", json=body) as r:
            self.status = r.status_code
            for line in r.iter_lines():
                self.lines.append(line)

    def join(self):
        self.thread.join(10)
        assert not self.thread.is_alive()
        return read_stream(self.lines)


def wait(condition, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return
        time.sleep(0.01)
    pytest.fail("condition not reached")


# --- slots (US3) ----------------------------------------------------------------------------------------------


def test_second_ask_is_busy_until_the_first_ends(ask_app):
    model, _, gated = gated_model()
    ask_app.models.append(model)
    first = Background(ask_app.client, ask_app.body())
    assert gated.reached.wait(5)
    r = ask_app.client.post("/api/v1/ask", json=ask_app.body())
    assert r.status_code == 429 and r.headers["Retry-After"] == "30"
    assert r.json() == {"error": {"kind": "busy", "message": "another question is being answered; try again later"}}
    assert ask_app.built == 1
    gated.gate.set()
    assert messages(first.join())[-1][0] == "answer"
    wait(lambda: ask_app.service.running() == 0)
    ask_app.models.append(scripted("x", "y", ClaimsReply(claims=[]))[0])
    assert ask_app.client.post("/api/v1/ask", json=ask_app.body()).status_code == 200


@pytest.mark.parametrize("ask_app", [{"limit": 2}], indirect=True)
def test_limit_two(ask_app):
    runs = [gated_model() for _ in range(2)]
    ask_app.models.extend(m for m, _, _ in runs)
    streams = [Background(ask_app.client, ask_app.body()) for _ in runs]
    for _, _, gated in runs:
        assert gated.reached.wait(5)
    assert ask_app.client.post("/api/v1/ask", json=ask_app.body()).status_code == 429
    for _, _, gated in runs:
        gated.gate.set()
    for s in streams:
        assert messages(s.join())[-1][0] == "answer"


def test_jobs_and_reads_are_not_blocked(ask_app, database_url, tmp_path):
    runner = JobRunner(database_url, PipelineLimits(), work_dir=tmp_path / "jobs")
    runner.start()
    try:
        client = TestClient(create_app(ask_app.store, runner, ask_app.service))
        model, _, gated = gated_model()
        ask_app.models.append(model)
        stream = Background(client, ask_app.body())
        assert gated.reached.wait(5)
        started = time.monotonic()
        graph = client.get("/api/v1/graph", params={"repository": "py-cycles", "snapshot": ask_app.snapshot})
        file = client.get("/api/v1/file", params={"repository": "py-cycles", "snapshot": ask_app.snapshot, "path": "loop/a.py"})
        assert graph.status_code == file.status_code == 200 and time.monotonic() - started < 1.0
        job = client.post("/api/v1/jobs/zip", params={"name": "app.zip"}, content=fixture_zip("py-flat"),
                          headers={"Content-Type": "application/zip"})
        assert job.status_code == 202
        assert wait_for_job(client, job.json()["id"])["stage"] == "done"
        gated.gate.set()
        assert messages(stream.join())[-1][0] == "answer"
    finally:
        runner.stop()


# --- disconnect and shutdown (US4) ------------------------------------------------------------------------------


def counts(store):
    with store._conn.cursor() as cur:
        return tuple(cur.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("analyses", "files", "blobs"))


def test_disconnect_stops_the_run(ask_app):
    model, script, gated = gated_model()
    ask_app.models.append(model)
    before = counts(ask_app.store)
    with ask_app.client.stream("POST", "/api/v1/ask", json=ask_app.body()) as r:
        for line in r.iter_lines():
            if line == "":
                break
        assert gated.reached.wait(5)
    gated.gate.set()
    wait(lambda: ask_app.service.running() == 0)
    assert len(script.replies) == 3  # nothing after the reply that was running
    assert counts(ask_app.store) == before
    ask_app.models.append(scripted("x", "y", ClaimsReply(claims=[]))[0])
    assert ask_app.client.post("/api/v1/ask", json=ask_app.body()).status_code == 200


def test_closing_the_stream_sets_stop(ask_app):
    model, _, gated = gated_model()
    ask_app.models.append(model)

    async def main():
        run = ask_app.service.open("py-cycles", ask_app.snapshot, "q", asyncio.get_running_loop())
        stream = run.stream()
        first = await stream.__anext__()
        assert first.startswith(b"event: step")
        await stream.aclose()
        return run

    run = asyncio.run(main())
    assert run.stop.is_set()
    gated.gate.set()
    run.thread.join(5)
    assert not run.thread.is_alive() and ask_app.service.running() == 0


def test_service_stop_stops_runs(ask_app):
    model, script, gated = gated_model()
    ask_app.models.append(model)
    stream = Background(ask_app.client, ask_app.body())
    assert gated.reached.wait(5)
    threading.Timer(0.2, gated.gate.set).start()
    started = time.monotonic()
    ask_app.service.stop(timeout=5)
    assert time.monotonic() - started < 5 and ask_app.service.running() == 0
    assert len(script.replies) == 3
    run = json.loads(messages(stream.join())[-1][2])
    assert run["answer"]["end"] == "stopped"
    r = ask_app.client.post("/api/v1/ask", json=ask_app.body())
    assert (r.status_code, r.json()["error"]["kind"]) == (503, "stopping")


# --- keep-alive (US5) ---------------------------------------------------------------------------------------


def test_keep_alive_during_silence(ask_app, monkeypatch):
    assert ask_module.KEEPALIVE_SECONDS == 15.0
    monkeypatch.setattr(ask_module, "KEEPALIVE_SECONDS", 0.2)
    model, _, gated = gated_model()
    ask_app.models.append(model)
    stream = Background(ask_app.client, ask_app.body())
    assert gated.reached.wait(5)
    time.sleep(1.0)
    gated.gate.set()
    got = stream.join()
    kinds = [k for k, _, _ in got]
    first_step_after_wait = kinds.index("ping")
    assert kinds[first_step_after_wait : first_step_after_wait + 3] == ["ping"] * 3
    steps = [m for m in messages(got) if m[0] == "step"]
    assert [int(i) for _, i, _ in steps] == list(range(1, len(steps) + 1))
    assert messages(got)[-1][0] == "answer"


def test_stop_between_open_and_thread_start(ask_app, monkeypatch):
    """`stop()` racing an `open()` that has registered its run but not started its thread (013 review)."""
    model, _, gated = gated_model()
    gated.gate.set()
    ask_app.models.append(model)
    real_start = threading.Thread.start
    errors = []

    def start(self):
        if self.name.startswith("graphora-ask"):
            try:
                ask_app.service.stop(timeout=1)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
        real_start(self)

    monkeypatch.setattr(threading.Thread, "start", start)
    ask_app.client.post("/api/v1/ask", json=ask_app.body())
    assert errors == []
    wait(lambda: ask_app.service.running() == 0)


def test_client_gone_before_the_stream_starts(ask_app, monkeypatch):
    """A request dropped before its stream starts never runs the agents and frees its slot (013 review)."""
    model, script, _ = gated_model()
    ask_app.models.append(model)

    async def never_started(self):
        return
        yield  # an async generator the response closes without advancing

    monkeypatch.setattr(ask_module.AskRun, "stream", never_started)
    ask_app.client.post("/api/v1/ask", json=ask_app.body())
    wait(lambda: ask_app.service.running() == 0)
    assert script.calls == []


def test_thread_that_cannot_start_frees_the_slot(ask_app, monkeypatch):
    """The system refusing a new thread ends the stream with an error and frees the slot (013 review)."""
    model, script, _ = gated_model()
    ask_app.models.append(model)
    real_start = threading.Thread.start

    def refuse(self):
        if self.name.startswith("graphora-ask"):
            raise RuntimeError("can't start new thread")
        real_start(self)

    monkeypatch.setattr(threading.Thread, "start", refuse)
    with ask_app.client.stream("POST", "/api/v1/ask", json=ask_app.body()) as r:
        got = messages(read_stream(r.iter_lines()))
    assert got == [("error", None, '{"message":"internal error"}')]
    assert ask_app.service.running() == 0 and script.calls == []
    monkeypatch.setattr(threading.Thread, "start", real_start)
    ask_app.models.append(scripted("x", "y", ClaimsReply(claims=[]))[0])
    assert ask_app.client.post("/api/v1/ask", json=ask_app.body()).status_code == 200


def test_slot_is_free_when_the_answer_arrives(ask_app, monkeypatch):
    """A follow-up sent on `answer` is not refused as busy, even if closing the connection is slow (013 review)."""
    from graphora.store import Store

    real_close = Store.close

    def slow_close(self):
        time.sleep(0.3)
        real_close(self)

    monkeypatch.setattr(Store, "close", slow_close)
    ask_app.models.append(scripted("x", "y", ClaimsReply(claims=[]))[0])
    with ask_app.client.stream("POST", "/api/v1/ask", json=ask_app.body()) as r:
        for line in r.iter_lines():
            if line.startswith("event: answer"):
                assert ask_app.service.running() == 0
                break
        else:
            pytest.fail("no answer")
