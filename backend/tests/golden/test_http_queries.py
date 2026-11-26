"""HTTP graph questions answer exactly what `graphora query --format json` answers, on every fixture's queries.json
(specs/018-http-queries SC-001, SC-002)."""

import json

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, analyze_fixture, run_query
from graphora.api import create_app

pytestmark = pytest.mark.db

HTTP = {"dependencies", "dependents", "impact", "neighbors", "cycles", "key_files", "projects"}

CASES = [
    pytest.param(p.parent.name, entry, id=f"{p.parent.name}-{i}-{entry['question']}")
    for p in sorted(FIXTURES.glob("*/queries.json"))
    for i, entry in enumerate(json.loads(p.read_text(encoding="utf-8")))
    if entry["question"] in HTTP
]

_ANALYSES = {}


def _flags(options):
    flags = ["--limit", str(options["limit"])] if "limit" in options else []
    if not options.get("include_type_only", True):
        flags.append("--no-type-only")
    if options.get("follow_barrels"):
        flags.append("--follow-barrels")
    if options.get("max_depth") is not None:
        flags += ["--max-depth", str(options["max_depth"])]
    if options.get("symbol") is not None:
        flags += ["--symbol", options["symbol"]]
    if options.get("level", "file") != "file":
        flags += ["--level", options["level"]]
    return flags


def _param(value):
    return ("true" if value else "false") if isinstance(value, bool) else str(value)


def stored(store, tmp_path, name):
    """The fixture stored under its name, and its stored graph written to a file for the CLI."""
    if name not in _ANALYSES:
        _ANALYSES[name] = analyze_fixture(name)
    analysis = _ANALYSES[name]
    store.put(name, analysis)
    graph = tmp_path / "g.json"
    graph.write_bytes(store.get_analysis(name, analysis.doc.snapshot).graph)
    return analysis.doc.snapshot, str(graph)


def ask(client, name, snapshot, question, **params):
    response = client.get(f"/api/v1/{question}", params={"repository": name, "snapshot": snapshot} | params)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/json"
    return response.content


@pytest.mark.parametrize(("name", "entry"), CASES)
def test_answer_equals_query(store, tmp_path, name, entry):
    snapshot, graph = stored(store, tmp_path, name)
    client = TestClient(create_app(store))
    options = ({} if entry["question"] == "projects" else {"limit": 500}) | entry["options"]
    target = [] if entry["target"] is None else [entry["target"]]
    params = {k: _param(v) for k, v in options.items()} | ({} if entry["target"] is None else {"target": entry["target"]})

    code, as_json, err = run_query(graph, entry["question"].replace("_", "-"), *target, *_flags(options), "--format", "json")
    assert (code, err) == (0, "")
    assert ask(client, name, snapshot, entry["question"], **params) == as_json
    assert ask(client, name, snapshot, entry["question"], **params) == as_json


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.iterdir() if (p / "repo").is_dir()))
def test_overview(store, tmp_path, name):
    snapshot, graph = stored(store, tmp_path, name)
    client = TestClient(create_app(store))
    code, as_json, err = run_query(graph, "overview", "--format", "json")
    assert (code, err) == (0, "")
    assert ask(client, name, snapshot, "overview") == as_json
    assert ask(client, name, snapshot, "overview") == as_json


DEFINED = [
    p.parent.name
    for p in sorted(FIXTURES.glob("*/expected.json"))
    if any(n.get("definitions") for n in json.loads(p.read_text(encoding="utf-8")).get("nodes", []))
]


@pytest.mark.parametrize("name", DEFINED)
def test_definitions(store, tmp_path, name):
    snapshot, graph = stored(store, tmp_path, name)
    client = TestClient(create_app(store))
    nodes = json.loads((FIXTURES / name / "expected.json").read_text(encoding="utf-8"))["nodes"]
    names = sorted({d["name"].rsplit(".", 1)[-1] for n in nodes for d in n.get("definitions", [])})
    assert names
    for symbol in names:
        code, as_json, err = run_query(graph, "definitions", symbol, "--limit", "500", "--format", "json")
        assert (code, err) == (0, "")
        assert ask(client, name, snapshot, "definitions", name=symbol, limit="500") == as_json
