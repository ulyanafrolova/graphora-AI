"""`graphora ask` (specs/012-agents contracts/cli.md, US4, tasks T031). The model is scripted: the suite is
offline."""

import io
import json
import sys
from pathlib import Path

import httpx
import pytest

import graphora.agents.model as model_module
from conftest import analyzed_graph
from graphora.agents.claims import ClaimItem, ClaimsReply
from graphora.agents.model import ModelUnavailable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from scripted_model import call, scripted  # noqa: E402


def run_ask(*args, stdin=b""):
    from graphora.cli import main

    out, err = io.StringIO(), io.StringIO()
    old = sys.stdout, sys.stderr, sys.stdin
    sys.stdout, sys.stderr = out, err
    sys.stdin = io.TextIOWrapper(io.BytesIO(stdin))
    try:
        code = main(["ask", *args])
    finally:
        sys.stdout, sys.stderr, sys.stdin = old
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def graph(tmp_path):
    path = tmp_path / "g.json"
    path.write_bytes(analyzed_graph("py-cycles"))
    return str(path)


@pytest.fixture
def model(monkeypatch):
    """Patches the model factory; returns the settings it was asked for and the scripts."""
    asked, scripts = [], []

    def factory(setting):
        asked.append(setting)
        m, script = scripted(
            call("dependents", target="loop/a.py"),
            "found c1 and c2",
            "no tools",
            ClaimsReply(claims=[ClaimItem(cite="c1"), ClaimItem(path="frontend.ts", line=1, target="loop/a.py")]),
            "still nothing",
            "no tools",
            ClaimsReply(claims=[]),
            "loop/c.py imports loop/a.py.",
        )
        scripts.append(script)
        return m

    monkeypatch.setattr(model_module, "model_from_setting", factory)
    monkeypatch.delenv("GRAPHORA_MODEL", raising=False)
    return asked, scripts


def test_text_answer(graph, model):
    code, out, err = run_ask("What breaks if I change loop/a.py?", "--graph", graph)
    assert code == 0 and err == ""
    for heading in ("Facts", "Likely", "Hypotheses (not proven)", "Summary"):
        assert f"\n{heading}\n" in out
    assert "- `loop/c.py` imports `loop/a.py` (name `a`) (loop/c.py:1@" in out
    assert "ended: answered" in out
    assert model[0] == ["ollama:qwen3:8b"]


def test_json_and_trace(graph, model, tmp_path):
    trace_file = tmp_path / "trace.jsonl"
    code, out, _ = run_ask("q", "--graph", graph, "--json", "--trace", str(trace_file))
    data = json.loads(out)
    assert code == 0 and list(data) == ["answer", "trace"] and out == json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    assert [json.loads(line) for line in trace_file.read_text().splitlines()] == data["trace"]
    code, out, err = run_ask("q", "--graph", graph, "--trace", "-")
    assert code == 0 and [json.loads(line)["n"] for line in err.splitlines()][:2] == [1, 2]


def test_no_summary_and_model_settings(graph, model, monkeypatch):
    asked, scripts = model
    code, out, _ = run_ask("q", "--graph", graph, "--no-summary", "--model", "x:y")
    assert code == 0 and asked == ["x:y"] and scripts[0].replies == ["loop/c.py imports loop/a.py."]
    monkeypatch.setenv("GRAPHORA_MODEL", "ollama:llama3.1:8b")
    run_ask("q", "--graph", graph)
    assert asked[-1] == "ollama:llama3.1:8b"


def test_graph_from_stdin(model):
    code, out, _ = run_ask("q", "--graph", "-", stdin=analyzed_graph("py-cycles"))
    assert code == 0 and "loop/c.py:1@" in out


@pytest.mark.parametrize(
    "args",
    [
        ["q"],
        ["q", "--graph", "g.json", "--snapshot", "s"],
        ["q", "--repository", "r"],
        ["  ", "--graph", "g.json"],
        ["q", "--graph", "g.json", "--database", "postgresql://x"],
    ],
)
def test_usage_errors(args, model):
    code, out, err = run_ask(*args)
    assert code == 2 and out == "" and err.startswith("graphora: error: ")


def test_model_unavailable(graph, monkeypatch):
    def factory(setting):
        raise ModelUnavailable(setting, "http://127.0.0.1:11434", "integration package missing")

    monkeypatch.setattr(model_module, "model_from_setting", factory)
    code, out, err = run_ask("q", "--graph", graph)
    assert (code, out) == (9, "")
    assert err == "graphora: error: model ollama:qwen3:8b unavailable at http://127.0.0.1:11434: integration package missing\n"


def test_model_fails_before_any_claim(graph, monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.setattr(model_module, "model_from_setting", lambda s: scripted(httpx.ConnectError("refused"))[0])
    code, out, err = run_ask("q", "--graph", graph)
    assert (code, out) == (9, "")
    assert err == "graphora: error: model ollama:qwen3:8b unavailable at http://127.0.0.1:11434: cannot connect\n"
    assert "Traceback" not in err


@pytest.mark.db
def test_store_pair_not_found(model, database_url, store):
    code, out, err = run_ask("q", "--repository", "nope", "--snapshot", "s", "--database", database_url)
    assert (code, out) == (8, "") and "repository not found: nope" in err
