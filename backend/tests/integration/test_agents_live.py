"""The agents with a live model (specs/012-agents FR-018, FR-023, SC-001, SC-002, SC-007, tasks T034). Skipped
unless GRAPHORA_TEST_MODEL names a model, e.g. `ollama:qwen3:8b`. Asserts structure only, never wording."""

import os
import socket
import time
from urllib.parse import urlsplit

import pytest

from conftest import analyze_fixture, analyzed_graph
from graphora.agents import ask, model_from_setting
from graphora.agents.limits import MAX_REVISIONS, MAX_TOOL_CALLS
from graphora.agents.model import ollama_address
from graphora.graph.load import loads
from graphora.graph.queries import index
from graphora.mcp import Served, from_store
from graphora.verify import verify_served

SETTING = os.environ.get("GRAPHORA_TEST_MODEL")
pytestmark = [pytest.mark.llm, pytest.mark.skipif(not SETTING, reason="set GRAPHORA_TEST_MODEL to run")]


@pytest.fixture
def _no_network(monkeypatch):
    """Replaces the suite's network ban for this module: only the model's address may be contacted (FR-018)."""
    parts = urlsplit(ollama_address())
    allowed = {(parts.hostname, parts.port or 11434)} | (
        {("localhost", parts.port or 11434), ("::1", parts.port or 11434)} if parts.hostname in ("127.0.0.1", "localhost") else set()
    )
    contacted = []
    real_connect, real_create = socket.socket.connect, socket.create_connection

    def check(address):
        host, port = address[0], address[1]
        contacted.append((host, port))
        if (host, port) not in allowed:
            raise AssertionError(f"network access outside the model: {host}:{port}")

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            check(address)
        return real_connect(self, address)

    def create_connection(address, *args, **kwargs):
        check(address)
        return real_create(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    return contacted


@pytest.fixture
def snapshot(request):
    """The stored analysis when a test database is configured, else the graph file."""
    if os.environ.get("GRAPHORA_TEST_DATABASE_URL"):
        store, url = request.getfixturevalue("store"), request.getfixturevalue("database_url")
        analysis = analyze_fixture("mixed-fullstack")
        store.put("mixed-fullstack", analysis)
        served = from_store(url, "mixed-fullstack", analysis.doc.snapshot)
        request.addfinalizer(served.store.close)
        return served
    return Served(index(loads(analyzed_graph("mixed-fullstack"))))


def test_live_answer_is_bounded_and_proven(snapshot, _no_network):
    started = time.monotonic()
    run = ask("What breaks if I change backend/app/models.py?", snapshot, model=model_from_setting(SETTING), setting=SETTING)
    elapsed = time.monotonic() - started
    answer = run.answer
    print(f"\n{SETTING}: {elapsed:.0f} s, end {answer.end}, {answer.counts}, {len(answer.facts)} facts")
    assert answer.end != "model_failed", run.error
    assert answer.counts["tool_calls"] <= MAX_TOOL_CALLS and answer.counts["revisions"] <= MAX_REVISIONS
    assert all(v.status == "verified" for v in verify_served([i.claim for i in answer.facts], snapshot))
    assert all(v.status == "heuristic" for v in verify_served([i.claim for i in answer.likely], snapshot))
    assert all(v.status == "rejected" for v in verify_served([i.claim for i in answer.hypotheses], snapshot))
    assert _no_network, "the model was never contacted"
