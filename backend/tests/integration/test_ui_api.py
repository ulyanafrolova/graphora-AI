"""Line counts, service info and the built UI served by the API (specs/019-frontend contracts/backend.md)."""

import pytest
from fastapi.testclient import TestClient

from conftest import analyze_fixture
from graphora.api import create_app
from graphora.api.ask import AskService
from graphora.ingest.walk import EXCLUDED_DIRS
from graphora.pipeline import PipelineLimits
from graphora.pipeline.jobs import JobRunner

pytestmark = pytest.mark.db

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "connect-src 'self'"
)
STORE_TOOLS = sorted(
    [
        "graph_overview",
        "find_definitions",
        "dependencies",
        "dependents",
        "impact",
        "neighbors",
        "cycles",
        "projects",
        "key_files",
        "hotspots",
        "components",
        "read_lines",
    ]
)


@pytest.fixture
def stored(store):
    analysis = analyze_fixture("py-cycles")
    store.put("py-cycles", analysis)
    return analysis


def test_files(store, stored):
    client = TestClient(create_app(store))
    snapshot = stored.doc.snapshot
    response = client.get("/api/v1/files", params={"repository": "py-cycles", "snapshot": snapshot})
    assert response.status_code == 200
    body = response.json()
    assert (body["repository"], body["snapshot"]) == ("py-cycles", snapshot)
    paths = [f["path"] for f in body["files"]]
    assert paths == sorted(paths) and "loop/a.py" in paths
    for f in body["files"]:
        assert set(f) == {"path", "has_text", "line_count"}
        assert f["line_count"] == store.get_file("py-cycles", snapshot, f["path"]).line_count


def test_files_errors(store, stored):
    client = TestClient(create_app(store))
    snapshot = stored.doc.snapshot
    assert client.get("/api/v1/files", params={"repository": "nope", "snapshot": snapshot}).status_code == 404
    assert client.get("/api/v1/files", params={"repository": "py-cycles", "snapshot": snapshot, "x": "1"}).status_code == 400
    store._conn.execute("UPDATE analyses SET schema_version = schema_version - 1")
    response = client.get("/api/v1/files", params={"repository": "py-cycles", "snapshot": snapshot})
    assert response.status_code == 409 and response.json()["error"]["kind"] == "stale"


def test_info_without_jobs_and_asks(store):
    body = TestClient(create_app(store)).get("/api/v1/info").json()
    assert body["ask"] == {"enabled": False, "model": None, "limits": {"tool_calls": 15, "revisions": 2}}
    assert body["jobs"] == {"enabled": False, "limits": None}
    assert [t["name"] for t in body["mcp_tools"]] == STORE_TOOLS
    assert all(t["description"] for t in body["mcp_tools"])
    assert body["version"]


def test_info_with_jobs_and_asks(store, database_url, tmp_path):
    limits = PipelineLimits(max_files=100)
    runner = JobRunner(database_url, limits, work_dir=tmp_path / "jobs")
    asks = AskService(store, database_url, "ollama:qwen3:8b", model_factory=lambda setting: None)
    try:
        client = TestClient(create_app(store, runner, asks))
        body = client.get("/api/v1/info").json()
        assert body["ask"] == {"enabled": True, "model": "ollama:qwen3:8b", "limits": {"tool_calls": 15, "revisions": 2}}
        assert body["jobs"] == {"enabled": True, "limits": limits.as_dict() | {"skipped": sorted(EXCLUDED_DIRS)}}
        assert client.get("/api/v1/info", params={"x": "1"}).status_code == 400
    finally:
        asks.stop(timeout=5)


@pytest.fixture
def ui(tmp_path):
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text("<!doctype html><title>Graphora</title>", encoding="utf-8")
    (folder / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("TOPSECRET", encoding="utf-8")
    return folder


def test_serves_ui(store, ui):
    client = TestClient(create_app(store, ui=ui))
    index = client.get("/")
    assert index.status_code == 200 and "Graphora" in index.text
    assert index.headers["content-security-policy"] == CSP
    script = client.get("/assets/app.js")
    assert script.status_code == 200 and script.text == "console.log(1)"
    assert script.headers["content-security-policy"] == CSP
    route = client.get("/r/py-cycles/content:abc/graph")
    assert route.status_code == 200 and "Graphora" in route.text


def test_api_paths_stay_json(store, ui):
    client = TestClient(create_app(store, ui=ui))
    response = client.get("/api/v1/nope")
    assert response.status_code == 404 and response.json()["error"]["kind"] == "not_found"
    assert client.get("/api/v1/info").status_code == 200


@pytest.mark.parametrize("path", ["/..%2fsecret.txt", "/assets/..%2f..%2fsecret.txt", "/%2e%2e/secret.txt"])
def test_no_files_outside_the_ui(store, ui, path):
    response = TestClient(create_app(store, ui=ui)).get(path)
    assert "TOPSECRET" not in response.text


def test_without_ui(store):
    response = TestClient(create_app(store)).get("/")
    assert response.status_code == 404 and response.json()["error"]["kind"] == "not_found"
