"""Graph question routes: defaults, targets and errors (specs/018-http-queries contracts/http-api.md)."""

import pytest
from fastapi.testclient import TestClient

from conftest import analyze_fixture, run_query
from graphora.api import create_app

pytestmark = pytest.mark.db

_ANALYSES = {}


@pytest.fixture
def client(store):
    return TestClient(create_app(store))


@pytest.fixture
def put(store, tmp_path):
    """Store a fixture; returns its snapshot and the stored graph as a file for the CLI."""

    def put(name):
        if name not in _ANALYSES:
            _ANALYSES[name] = analyze_fixture(name)
        snapshot = _ANALYSES[name].doc.snapshot
        store.put(name, _ANALYSES[name])
        graph = tmp_path / f"{name}.json"
        graph.write_bytes(store.get_analysis(name, snapshot).graph)
        return snapshot, str(graph)

    return put


def get(client, question, repo, snapshot, **params):
    return client.get(f"/api/v1/{question}", params={"repository": repo, "snapshot": snapshot} | params)


def cli(graph, *args):
    code, out, err = run_query(graph, *args, "--format", "json")
    assert (code, err) == (0, "")
    return out


def error(response, status, kind):
    assert response.status_code == status, response.text
    assert response.json()["error"]["kind"] == kind
    return response.json()["error"]["message"]


def test_default_limit(client, put):
    snapshot, graph = put("ts-app")
    response = get(client, "dependents", "ts-app", snapshot, target="src/util.ts")
    assert response.json()["options"]["limit"] == 50
    assert response.content == cli(graph, "dependents", "src/util.ts", "--limit", "50")


def test_limit_cuts(client, put):
    snapshot, _ = put("ts-app")
    none = get(client, "dependents", "ts-app", snapshot, target="src/util.ts", limit="0").json()
    assert (none["items"], none["total"], none["truncated"]) == ([], 2, True)
    one = get(client, "dependents", "ts-app", snapshot, target="src/util.ts", limit="1").json()
    assert (len(one["items"]), one["total"], one["truncated"]) == (1, 2, True)


@pytest.mark.parametrize("target", ["./src/util.ts", "src/util.ts/", "file:src/util.ts"])
def test_target_spellings(client, put, target):
    snapshot, _ = put("ts-app")
    same = get(client, "dependents", "ts-app", snapshot, target="src/util.ts")
    assert same.status_code == 200
    assert get(client, "dependents", "ts-app", snapshot, target=target).content == same.content


def test_target_not_found(client, put):
    snapshot, _ = put("ts-app")
    assert "is not in snapshot" in error(get(client, "impact", "ts-app", snapshot, target="nope.ts"), 404, "not_found")
    message = error(get(client, "neighbors", "ts-app", snapshot, target="node_modules/x.js"), 404, "not_found")
    assert "excluded_dir" in message


@pytest.mark.parametrize("target", ["../x", "/etc/passwd", "a\\b"])
def test_invalid_path(client, put, target):
    snapshot, _ = put("ts-app")
    error(get(client, "dependencies", "ts-app", snapshot, target=target), 400, "bad_request")


def test_options_equal_the_cli(client, put):
    snapshot, graph = put("ts-app")
    response = get(client, "dependents", "ts-app", snapshot, target="src/util.ts", symbol="helper")
    assert response.content == cli(graph, "dependents", "src/util.ts", "--symbol", "helper", "--limit", "50")
    response = get(client, "impact", "ts-app", snapshot, target="src/util.ts", max_depth="1", follow_barrels="true")
    assert response.content == cli(graph, "impact", "src/util.ts", "--max-depth", "1", "--follow-barrels", "--limit", "50")


def test_project_level(client, put):
    snapshot, graph = put("csharp-multiproject")
    response = get(client, "impact", "csharp-multiproject", snapshot, target="src/Core/Core.csproj", level="project")
    assert response.status_code == 200
    assert response.content == cli(graph, "impact", "src/Core/Core.csproj", "--level", "project", "--limit", "50")


def test_key_files_default_limit(client, put):
    snapshot, graph = put("ts-app")
    response = get(client, "key_files", "ts-app", snapshot)
    assert response.json()["options"]["limit"] == 10
    assert response.content == cli(graph, "key-files")


def test_projects_without_csharp(client, put):
    snapshot, graph = put("ts-app")
    response = get(client, "projects", "ts-app", snapshot)
    assert response.status_code == 200
    assert response.content == cli(graph, "projects")


@pytest.mark.parametrize("question", ["overview", "projects"])
@pytest.mark.parametrize("param", [{"limit": "1"}, {"include_type_only": "true"}])
def test_no_options(client, put, question, param):
    snapshot, _ = put("ts-app")
    error(get(client, question, "ts-app", snapshot, **param), 400, "bad_request")


def test_cycles_without_type_only(client, put):
    snapshot, graph = put("py-cycles")
    response = get(client, "cycles", "py-cycles", snapshot, include_type_only="false")
    assert response.content == cli(graph, "cycles", "--no-type-only", "--limit", "50")


def test_unknown_name(client, put):
    snapshot, graph = put("ts-app")
    response = get(client, "definitions", "ts-app", snapshot, name="NoSuchName")
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.content == cli(graph, "definitions", "NoSuchName", "--limit", "50")


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({}, "missing parameter: name"),
        ({"name": ""}, "missing parameter: name"),
        ({"name": "x", "target": "x"}, "unknown parameter: target"),
        ({"name": "x", "include_type_only": "true"}, "unknown parameter: include_type_only"),
    ],
)
def test_definitions_parameters(client, put, params, message):
    snapshot, _ = put("ts-app")
    assert error(get(client, "definitions", "ts-app", snapshot, **params), 400, "bad_request") == message


ERRORS = [
    ("impact", {"target": "src/util.ts", "other": "1"}, 400, "bad_request"),
    ("impact", {}, 400, "bad_request"),
    ("impact", {"target": ""}, 400, "bad_request"),
    ("cycles", {"include_type_only": "yes"}, 400, "bad_request"),
    ("cycles", {"limit": "x"}, 400, "bad_request"),
    ("cycles", {"limit": "501"}, 400, "bad_request"),
    ("cycles", {"limit": "-1"}, 400, "bad_request"),
    ("cycles", {"level": "module"}, 400, "bad_request"),
    ("impact", {"target": "src/util.ts", "max_depth": "0"}, 400, "bad_request"),
    ("cycles", {"symbol": "x"}, 400, "bad_request"),
    ("dependents", {"target": "src/util.ts", "max_depth": "1"}, 400, "bad_request"),
    ("dependents", {"target": "src/util.ts", "symbol": ""}, 400, "bad_request"),
    ("dependents", {"target": "src/util.ts", "level": "project", "symbol": "helper"}, 400, "bad_request"),
    ("impact", {"target": "src/util.ts", "level": "project", "follow_barrels": "true"}, 400, "bad_request"),
    ("cycles", {"level": "project", "include_type_only": "false"}, 400, "bad_request"),
    ("neighbors", {"target": "src/util.ts", "level": "file"}, 400, "bad_request"),
]


@pytest.mark.parametrize(("question", "params", "status", "kind"), ERRORS)
def test_errors(client, put, question, params, status, kind):
    snapshot, _ = put("ts-app")
    response = get(client, question, "ts-app", snapshot, **params)
    assert set(response.json()) == {"error"} and set(response.json()["error"]) == {"kind", "message"}
    error(response, status, kind)


def test_repeated_parameter(client, put):
    snapshot, _ = put("ts-app")
    response = client.get(f"/api/v1/cycles?repository=ts-app&snapshot={snapshot}&limit=1&limit=2")
    assert error(response, 400, "bad_request") == "parameter given more than once: limit"


def test_missing_repository_or_snapshot(client, put):
    snapshot, _ = put("ts-app")
    assert error(get(client, "overview", "nope", snapshot), 404, "not_found") == "repository not found: nope"
    message = error(get(client, "overview", "ts-app", "content:0000000000000000"), 404, "not_found")
    assert message.startswith("snapshot not found")
    error(client.get("/api/v1/cycles", params={"snapshot": snapshot}), 400, "bad_request")


ROUTES = {
    "dependencies": {"target": "src/util.ts"},
    "dependents": {"target": "src/util.ts"},
    "impact": {"target": "src/util.ts"},
    "neighbors": {"target": "src/util.ts"},
    "cycles": {},
    "key_files": {},
    "definitions": {"name": "helper"},
    "overview": {},
    "projects": {},
}


def test_stale(store, client, put):
    snapshot, _ = put("ts-app")
    store._conn.execute("UPDATE analyses SET schema_version = schema_version - 1")
    for question, params in ROUTES.items():
        message = error(get(client, question, "ts-app", snapshot, **params), 409, "stale")
        assert message.endswith("analyze it again")


HOSTILE = "<script>alert(1)</script>" + "x" * 10_000


@pytest.mark.parametrize(
    ("question", "params"),
    [
        ("cycles", {"limit": HOSTILE}),
        ("cycles", {"include_type_only": HOSTILE}),
        ("cycles", {"level": HOSTILE}),
        ("impact", {"target": "src/util.ts", "max_depth": HOSTILE}),
        ("dependents", {"target": "src/util.ts", "level": "project", "symbol": HOSTILE}),
        ("overview", {"other": HOSTILE}),
    ],
)
def test_no_echo(client, put, question, params):
    snapshot, _ = put("ts-app")
    response = get(client, question, "ts-app", snapshot, **params)
    assert response.status_code == 400
    assert "<script>" not in response.text and "xxxx" not in response.text
