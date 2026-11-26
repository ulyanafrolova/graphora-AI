"""GET /api/v1/hotspots answers from the stored graph (specs/014-hotspots contracts/interfaces.md)."""

import dataclasses

import pytest
from fastapi.testclient import TestClient

from conftest import analyze_dir
from graphora.api import create_app
from graphora.graph.model import not_available
from graphora.graph.queries import hotspots, index
from graphora.graph.results import dumps
from history_repos import make_repo

pytestmark = pytest.mark.db

COMMITS = [
    {"files": {"a.py": b"import b\n", "b.py": b"x = 1\n", "c.py": b"import a\n"}},
    {"files": {"b.py": b"x = 2\n"}},
    {"files": {"a.py": b"import b\nimport os\n"}},
]


@pytest.fixture
def stored(store, tmp_path):
    make_repo(tmp_path / "app", COMMITS)
    analysis = analyze_dir(tmp_path / "app")
    store.put("app", analysis)
    return analysis


@pytest.fixture
def client(store):
    return TestClient(create_app(store))


def get(client, **params):
    return client.get("/api/v1/hotspots", params=params)


def test_answer_is_the_query(client, stored):
    response = get(client, repository="app", snapshot=stored.doc.snapshot, limit=1)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.content == dumps(hotspots(index(stored.doc), limit=1))
    full = get(client, repository="app", snapshot=stored.doc.snapshot, include_type_only="false")
    assert full.content == dumps(hotspots(index(stored.doc), include_type_only=False))
    assert [i["node"] for i in full.json()["items"]] == ["file:b.py", "file:a.py"]


def test_not_found(client, stored):
    assert get(client, repository="nope", snapshot=stored.doc.snapshot).status_code == 404
    assert get(client, repository="app", snapshot="content:0000000000000000").status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"limit": "x"},
        {"limit": "-1"},
        {"include_type_only": "yes"},
        {"other": "1"},
    ],
)
def test_bad_parameters(client, stored, params):
    response = get(client, repository="app", snapshot=stored.doc.snapshot, **params)
    assert response.status_code == 400


def test_repeated_parameter(client, stored):
    url = f"/api/v1/hotspots?repository=app&snapshot={stored.doc.snapshot}&limit=1&limit=2"
    assert client.get(url).status_code == 400


def test_history_not_available(store, client, stored):
    doc = dataclasses.replace(stored.doc, history=not_available("zip"))
    store.put("zip-app", dataclasses.replace(stored, doc=doc))
    response = get(client, repository="zip-app", snapshot=doc.snapshot)
    assert response.status_code == 200
    assert response.json()["items"] == [] and response.json()["history"]["reason"] == "zip"


def test_older_schema(store, client, stored):
    old = stored.doc.snapshot
    graph = store.get_analysis("app", old).graph.replace(b'"schema_version": 8', b'"schema_version": 7')
    store._conn.execute(
        "UPDATE analyses SET graph = %s, schema_version = 7 WHERE repository = 'app' AND snapshot = %s", (graph, old)
    )
    response = get(client, repository="app", snapshot=old)
    assert response.status_code == 409
    assert response.json()["error"] == {
        "kind": "stale",
        "message": f"app {old} was analyzed with graph schema 7; analyze it again",
    }
