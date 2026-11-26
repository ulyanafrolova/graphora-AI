"""`POST /api/v1/ask`: the stream and the refusals (specs/013-ask-sse US1, US2, SC-001–SC-003, tasks T009,
T013). Scripted model, stored `py-cycles`."""

import io
import json
import sys
import time
from pathlib import Path

import httpx
import pytest

import graphora.agents.model as model_module
import graphora.api.ask as ask_module
from conftest import FIXTURES
from graphora.agents import ask
from graphora.agents.claims import ClaimItem, ClaimsReply
from graphora.agents.model import ModelUnavailable
from graphora.mcp import from_store
from sse import messages, read_stream

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from scripted_model import Gated, call, scripted  # noqa: E402

pytestmark = pytest.mark.db


def what_breaks():
    return [
        call("dependents", target="loop/a.py"),
        "MODEL TEXT loop/a.py is imported by c1 and c2",
        "MODEL TEXT no tools",
        ClaimsReply(
            claims=[
                ClaimItem(statement="MODEL TEXT", cite="c1"),
                ClaimItem(statement="MODEL TEXT", cite="c2"),
                ClaimItem(statement="MODEL TEXT", path="frontend.ts", line=1, target="loop/a.py"),
            ]
        ),
        "MODEL TEXT nothing more",
        "MODEL TEXT no tools",
        ClaimsReply(claims=[]),
        "Changing loop/a.py breaks loop/c.py and user.py.",
    ]


def post(world, body=None, **kwargs):
    """(status, headers, parsed stream or JSON body)."""
    with world.client.stream("POST", "/api/v1/ask", json=world.body() if body is None else body, **kwargs) as r:
        lines = list(r.iter_lines())
        if r.headers["content-type"].startswith("text/event-stream"):
            return r.status_code, r.headers, read_stream(lines)
        return r.status_code, r.headers, json.loads("".join(lines))


def cli_json(world, database_url, monkeypatch, replies):
    from graphora.cli import main

    monkeypatch.setattr(model_module, "model_from_setting", lambda s: scripted(*replies)[0])
    out = io.StringIO()
    old = sys.stdout
    sys.stdout = out
    try:
        code = main(["ask", world.body()["question"], "--repository", "py-cycles", "--snapshot", world.snapshot, "--database", database_url, "--json"])
    finally:
        sys.stdout = old
    assert code == 0
    return json.loads(out.getvalue())


def test_stream_equals_direct_run_and_cli(ask_app, database_url, monkeypatch):
    ask_app.models.append(scripted(*what_breaks())[0])
    status, headers, stream = post(ask_app)
    assert status == 200 and headers["content-type"].startswith("text/event-stream")
    got = messages(stream)
    steps, last = got[:-1], got[-1]
    assert all(kind == "step" for kind, _, _ in steps) and last[0] == "answer"
    assert [int(i) for _, i, _ in steps] == list(range(1, len(steps) + 1))

    served = from_store(database_url, "py-cycles", ask_app.snapshot)
    try:
        direct = ask(ask_app.body()["question"], served, model=scripted(*what_breaks())[0], setting="scripted:test")
    finally:
        served.store.close()
    assert [json.loads(d) for _, _, d in steps] == [e.to_dict() for e in direct.trace]
    answer = json.loads(last[2])
    assert answer == direct.to_dict() == cli_json(ask_app, database_url, monkeypatch, what_breaks())
    assert [f["cite"].split("@")[0] for f in answer["answer"]["facts"]] == ["loop/c.py:1", "user.py:1"]


def test_rejected_claim_steps_come_first(ask_app):
    ask_app.models.append(scripted(*what_breaks())[0])
    _, _, stream = post(ask_app)
    kinds = [json.loads(d)["kind"] for k, _, d in messages(stream) if k == "step"]
    assert kinds.index("verdict") < kinds.index("hypothesis") < kinds.index("revision")
    answer = json.loads(messages(stream)[-1][2])["answer"]
    assert [h["cite"].split("@")[0] for h in answer["hypotheses"]] == ["frontend.ts:1"]
    assert all("frontend.ts" not in f["cite"] for f in answer["facts"])


def test_model_failure_mid_run_ends_with_answer(ask_app, monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    ask_app.models.append(
        scripted(
            call("dependents", target="loop/a.py"),
            "found",
            "no tools",
            ClaimsReply(claims=[ClaimItem(cite="c1"), ClaimItem(path="frontend.ts", line=1, target="loop/a.py")]),
            httpx.ConnectError("refused"),
        )[0]
    )
    _, _, stream = post(ask_app)
    kind, _, data = messages(stream)[-1]
    run = json.loads(data)
    assert kind == "answer" and run["answer"]["end"] == "model_failed" and run["error"]
    assert [f["cite"].split("@")[0] for f in run["answer"]["facts"]] == ["loop/c.py:1"]


def test_internal_error_ends_with_error_message(ask_app, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(ask_module, "ask", broken)
    ask_app.models.append(scripted()[0])
    _, _, stream = post(ask_app)
    assert messages(stream) == [("error", None, '{"message":"internal error"}')]
    assert ask_app.service.running() == 0


def test_steps_carry_no_file_model_or_question_text(ask_app):
    ask_app.models.append(scripted(*what_breaks())[0])
    question = "QUESTION TEXT: what breaks if I change loop/a.py?"
    _, _, stream = post(ask_app, ask_app.body(question))
    steps = " ".join(d for k, _, d in messages(stream) if k == "step")
    lines = [ln for p in (FIXTURES / "py-cycles" / "repo").rglob("*.py") for ln in p.read_text().splitlines() if len(ln) > 8]
    assert "MODEL TEXT" not in steps and "QUESTION TEXT" not in steps
    assert not any(ln in steps for ln in lines)
    assert json.loads(messages(stream)[-1][2])["answer"]["question"] == question


def test_first_step_before_the_first_model_reply(ask_app):
    gated = Gated(call("dependents", target="loop/a.py"))
    rest = what_breaks()[1:]
    ask_app.models.append(scripted(gated, *rest)[0])
    started = time.monotonic()
    with ask_app.client.stream("POST", "/api/v1/ask", json=ask_app.body()) as r:
        lines = r.iter_lines()
        first = []
        for line in lines:
            first.append(line)
            if line == "":
                break
        elapsed = time.monotonic() - started
        assert not gated.gate.is_set()
        assert read_stream(first)[0][0] == "step" and elapsed < 1.0
        gated.gate.set()
        list(lines)


# --- refusals (US2) -----------------------------------------------------------------------------------------


def refused(world, body, status, kind, message, **kwargs):
    started = time.monotonic()
    code, headers, data = post(world, body, **kwargs)
    assert time.monotonic() - started < 1.0
    assert (code, data) == (status, {"error": {"kind": kind, "message": message}})
    assert headers["content-type"] == "application/json"
    return headers


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ([], "the body must be a JSON object"),
        ({"repository": "py-cycles", "snapshot": "s", "question": "q", "x": 1}, "unknown key: x"),
        ({"repository": "py-cycles", "snapshot": "s"}, "missing question"),
        ({"repository": "py-cycles", "snapshot": "s", "question": "x" * 2001}, "question is longer than 2000 characters"),
    ],
)
def test_bad_bodies(ask_app, body, message):
    refused(ask_app, body, 400, "bad_request", message)
    assert ask_app.built == 0 and ask_app.service.running() == 0


def test_query_parameter_is_refused(ask_app):
    refused(ask_app, ask_app.body(), 400, "bad_request", "unknown parameter: x", params={"x": "1"})


def test_not_found_loads_no_graph(ask_app, monkeypatch):
    loads = []
    monkeypatch.setattr(ask_module, "from_store", lambda *a: loads.append(a))
    refused(ask_app, ask_app.body(repository="nope"), 404, "not_found", "repository not found: nope")
    refused(ask_app, ask_app.body(snapshot="nope"), 404, "not_found", "snapshot not found: py-cycles nope")
    assert loads == [] and ask_app.built == 0 and ask_app.service.running() == 0


def test_unusable_model_setting(ask_app):
    def factory(setting):
        ask_app.built += 1
        raise ModelUnavailable(setting, "the nope API", "Unsupported provider='nope'.")

    ask_app.service.model_factory = factory
    refused(ask_app, ask_app.body(), 503, "model_unavailable", "model scripted:test unavailable at the nope API: Unsupported provider='nope'.")
    assert ask_app.built == 1 and ask_app.service.running() == 0
    ask_app.service.model_factory = ask_app.factory
    ask_app.models.append(scripted(*what_breaks())[0])
    assert post(ask_app)[0] == 200


def test_bad_context_size_is_503(ask_app, monkeypatch):
    monkeypatch.setenv("GRAPHORA_MODEL_CTX", "8k")
    ask_app.service.model_factory = None
    ask_app.service.setting = "ollama:qwen3:8b"
    code, _, data = post(ask_app)
    assert (code, data["error"]["kind"]) == (503, "model_unavailable")
    assert "GRAPHORA_MODEL_CTX must be a positive integer" in data["error"]["message"]
    assert ask_app.service.running() == 0
