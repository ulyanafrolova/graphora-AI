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


def get(client, question, name, snapshot, **params):
    return client.get(f"/api/v1/{question}", params={"repository": name, "snapshot": snapshot} | params)


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
