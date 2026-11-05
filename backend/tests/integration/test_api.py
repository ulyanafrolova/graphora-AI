"""The read-only HTTP API (005 contracts/http-api.md; FR-012 … FR-019, SC-001, SC-005)."""

from __future__ import annotations

import builtins
import os
import threading

import pytest
from dulwich import porcelain
from fastapi.testclient import TestClient

from conftest import FIXTURES, analyze_dir, analyze_fixture, run_analyze
from graphora.api import create_app
from graphora.store import Store, StoreUnavailable

pytestmark = pytest.mark.db


@pytest.fixture
def client(store):
    return TestClient(create_app(store), raise_server_exceptions=False)


def _error(response, status, kind):
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert set(body) == {"error"} and body["error"]["kind"] == kind
    return body["error"]["message"]


# --- repositories ----------------------------------------------------------------------------------------


def test_repositories(store, client, tmp_path):
    assert client.get("/api/v1/repositories").content == b'{"repositories":[]}'
    flat, ts = analyze_fixture("py-flat"), analyze_fixture("ts-app")
    store.put("ts-app", ts)
    store.put("py-flat", flat)
    (tmp_path / "a.py").write_text("")
    other = analyze_dir(tmp_path)
    store.put("py-flat", other)
    response = client.get("/api/v1/repositories")
    assert response.status_code == 200
    snaps = sorted([flat.doc.snapshot, other.doc.snapshot])
    expected = (
        '{"repositories":[{"name":"py-flat","snapshots":["%s","%s"]},{"name":"ts-app","snapshots":["%s"]}]}'
        % (snaps[0], snaps[1], ts.doc.snapshot)
    )
    assert response.content == expected.encode()
    assert client.get("/api/v1/repositories").content == response.content


# --- graph -----------------------------------------------------------------------------------------------


def test_graph_is_the_stored_bytes(store, client):
    analysis = analyze_fixture("mixed-fullstack")
    store.put("mixed", analysis)
    params = {"repository": "mixed", "snapshot": analysis.doc.snapshot}
    first = client.get("/api/v1/graph", params=params)
    assert first.status_code == 200
    assert first.headers["content-type"] == "application/json"
    assert first.content == run_analyze(FIXTURES / "mixed-fullstack" / "repo")[1]
    assert client.get("/api/v1/graph", params=params).content == first.content


def test_graph_not_found(store, client):
    analysis = analyze_fixture("py-flat")
    store.put("py-flat", analysis)
    message = _error(client.get("/api/v1/graph", params={"repository": "nope", "snapshot": analysis.doc.snapshot}), 404, "not_found")
    assert message == "repository not found: nope"
    message = _error(client.get("/api/v1/graph", params={"repository": "py-flat", "snapshot": "content:0000000000000000"}), 404, "not_found")
    assert message == "snapshot not found: py-flat content:0000000000000000"


def test_dirty_snapshot_needs_encoded_plus(store, client, tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.py").write_text("import os\n")
    repo = porcelain.init(str(root))
    porcelain.add(repo, [str(root / "a.py")])
    porcelain.commit(repo, message=b"init", author=b"T <t@example.com>", committer=b"T <t@example.com>")
    repo.close()
    (root / "a.py").write_text("import sys\n")
    analysis = analyze_dir(root)
    snapshot = analysis.doc.snapshot
    assert "+dirty:" in snapshot
    store.put("r", analysis)
    assert client.get(f"/api/v1/graph?repository=r&snapshot={snapshot.replace('+', '%2B')}").status_code == 200
    _error(client.get(f"/api/v1/graph?repository=r&snapshot={snapshot}"), 404, "not_found")


# --- file ------------------------------------------------------------------------------------------------


@pytest.fixture
def flat(store):
    analysis = analyze_fixture("py-flat")
    store.put("py-flat", analysis)
    path = next(f.path for f in analysis.doc.files if f.path.endswith(".py") and analysis.contents.get(f.path, b"").count(b"\n") >= 3)
    return {"repository": "py-flat", "snapshot": analysis.doc.snapshot, "path": path}


def test_file_whole_and_range(client, flat):
    text = (FIXTURES / "py-flat" / "repo" / flat["path"]).read_text(encoding="utf-8").splitlines()
    whole = client.get("/api/v1/file", params=flat)
    assert whole.status_code == 200
    body = whole.json()
    assert body["path"] == flat["path"] and body["has_text"] is True
    assert body["line_count"] == len(text) and (body["start"], body["end"]) == (1, len(text))
    assert [line["text"] for line in body["lines"]] == text
    part = client.get("/api/v1/file", params={**flat, "start": 2, "end": 3}).json()
    assert part["lines"] == [{"n": 2, "text": text[1]}, {"n": 3, "text": text[2]}]
    assert client.get("/api/v1/file", params={**flat, "start": 2, "end": 3}).content == client.get(
        "/api/v1/file", params={**flat, "start": 2, "end": 3}
    ).content


def test_file_without_text(store, client, tmp_path):
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    analysis = analyze_dir(tmp_path)
    store.put("img", analysis)
    params = {"repository": "img", "snapshot": analysis.doc.snapshot, "path": "logo.png"}
    response = client.get("/api/v1/file", params=params)
    assert response.content == b'{"end":0,"has_text":false,"line_count":0,"lines":[],"path":"logo.png","start":0}'
    _error(client.get("/api/v1/file", params={**params, "start": 1}), 400, "bad_request")


@pytest.mark.parametrize(
    "path",
    ["../../etc/passwd", "/etc/passwd", "%2e%2e/x", "a\\b.py", "./{p}", "{P}", "{p}/", ".venv/lib.py", ""],
)
def test_hostile_paths(client, flat, monkeypatch, path):
    path = path.replace("{p}", flat["path"]).replace("{P}", flat["path"].upper())
    real_open, real_os_open = builtins.open, os.open
    opened = []

    def spy_open(file, *args, **kwargs):
        opened.append(file)
        return real_open(file, *args, **kwargs)

    def spy_os_open(file, *args, **kwargs):
        opened.append(file)
        return real_os_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(os, "open", spy_os_open)
    response = client.get("/api/v1/file", params={**flat, "path": path})
    monkeypatch.undo()
    if path == "":
        _error(response, 400, "bad_request")
    else:
        assert _error(response, 404, "not_found") == f"path not found in snapshot: {path}"
    assert opened == []


def test_path_of_another_snapshot(store, client, flat, tmp_path):
    (tmp_path / "only_here.py").write_text("")
    other = analyze_dir(tmp_path)
    store.put("py-flat", other)
    _error(client.get("/api/v1/file", params={**flat, "path": "only_here.py"}), 404, "not_found")


def test_file_not_found_names_the_missing_part(client, flat):
    assert _error(client.get("/api/v1/file", params={**flat, "repository": "nope"}), 404, "not_found") == "repository not found: nope"
    message = _error(client.get("/api/v1/file", params={**flat, "snapshot": "content:0000000000000000"}), 404, "not_found")
    assert message == "snapshot not found: py-flat content:0000000000000000"


@pytest.mark.parametrize(
    "query, message",
    [
        ("repository=py-flat&snapshot={s}", "missing parameter: path"),
        ("repository=py-flat&snapshot={s}&path={p}&x=1", "unknown parameter: x"),
        ("repository=py-flat&snapshot={s}&path={p}&start=abc", "start must be an integer"),
        ("repository=py-flat&snapshot={s}&path={p}&start=0", "start must be at least 1"),
        ("repository=py-flat&snapshot={s}&path={p}&start=3&end=2", "end must not be less than start"),
        ("repository=py-flat&snapshot={s}&path={p}&start=999", None),
        ("repository=py-flat&repository=x&snapshot={s}&path={p}", "parameter given more than once: repository"),
    ],
)
def test_bad_requests(client, flat, query, message):
    query = query.replace("{s}", flat["snapshot"]).replace("{p}", flat["path"])
    response = client.get(f"/api/v1/file?{query}")
    got = _error(response, 400, "bad_request")
    if message is not None:
        assert got == message
    assert "detail" not in response.json()


def test_unknown_parameter_on_lists(client):
    assert _error(client.get("/api/v1/repositories?all=1"), 400, "bad_request") == "unknown parameter: all"


# --- errors and read-only --------------------------------------------------------------------------------


def test_store_unavailable(client, monkeypatch):
    def down(self):
        raise StoreUnavailable("connection refused")

    monkeypatch.setattr(Store, "list_repositories", down)
    assert _error(client.get("/api/v1/repositories"), 503, "store_unavailable") == "store unavailable"


def test_internal_error_hides_details(client, monkeypatch):
    def broken(self):
        raise RuntimeError("secret /Users/someone/x")

    monkeypatch.setattr(Store, "list_repositories", broken)
    response = client.get("/api/v1/repositories")
    assert _error(response, 500, "internal") == "internal error"
    assert b"secret" not in response.content and b"/Users" not in response.content


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
@pytest.mark.parametrize("path", ["/api/v1/repositories", "/api/v1/graph", "/api/v1/file"])
def test_only_get(client, method, path):
    _error(getattr(client, method)(path), 405, "method_not_allowed")


def test_only_three_read_endpoints(client):
    paths = client.app.openapi()["paths"]
    assert {p: sorted(v) for p, v in paths.items()} == {
        "/api/v1/repositories": ["get"],
        "/api/v1/graph": ["get"],
        "/api/v1/file": ["get"],
    }
    _error(client.get("/api/v1/import"), 404, "not_found")


def test_concurrent_graph_requests(store, client):
    analysis = analyze_fixture("ts-monorepo")
    store.put("mono", analysis)
    expected = store.get_analysis("mono", analysis.doc.snapshot).graph
    results = []

    def fetch():
        results.append(client.get("/api/v1/graph", params={"repository": "mono", "snapshot": analysis.doc.snapshot}).content)

    threads = [threading.Thread(target=fetch) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [expected] * 8
