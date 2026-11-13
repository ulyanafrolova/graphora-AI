"""US1: a GitHub link becomes a stored, queryable graph over HTTP (specs/010-end-to-end-pipeline tasks T011)."""

import json

import pytest

from conftest import run_analyze
from graphora.mcp import create_server, from_store
from jobs_helpers import fixture_tarball, stages_seen, wait_for_job
from mcp_client import call

SHA = "1111111111111111111111111111111111111111"
LINK = "https://github.com/o/ts-app"
ORDER = ["queued", "resolving", "fetching", "analyzing", "storing", "done"]

pytestmark = pytest.mark.db


@pytest.fixture
def github(fake_gh):
    fake_gh.serve("https://api.github.com/repos/o/ts-app/commits/HEAD", body=SHA.encode())
    fake_gh.serve(f"https://codeload.github.com/o/ts-app/tar.gz/{SHA}", body=fixture_tarball("ts-app", SHA))
    return fake_gh


def _start(client, **body):
    response = client.post("/api/v1/jobs", json=body)
    assert response.status_code == 202, response.text
    return json.loads(response.content)


def _cli(argument):
    """A plain run: an `--store` run after the job would only reuse the stored bytes."""
    code, out, err = run_analyze(argument)
    assert code == 0, err
    return out, err


def test_start_answers_at_once(job_app, github):
    client, _ = job_app
    started = _start(client, github=LINK)
    assert started["stage"] in ORDER
    assert started["source"] == {"kind": "github", "ref": None, "repository": "github.com/o/ts-app"}
    assert started["result"] is None and started["error"] is None


def test_stages_move_forward(job_app, github):
    client, _ = job_app
    seen = stages_seen(client, _start(client, github=LINK)["id"])
    assert seen[-1] == "done"
    assert [s for s in ORDER if s in seen] == seen


def test_done_names_the_stored_analysis(job_app, github):
    client, _ = job_app
    done = wait_for_job(client, _start(client, github=LINK)["id"])
    result = done["result"]
    assert (result["repository"], result["snapshot"], result["action"]) == ("github.com/o/ts-app", SHA, "stored")

    graph = client.get("/api/v1/graph", params={"repository": result["repository"], "snapshot": SHA})
    assert graph.status_code == 200
    out, err = _cli(LINK)
    assert graph.content == out
    summary = f"analyzed {result['files']} files, {result['edges']} edges ({result['unresolved']} unresolved)"
    assert summary in err


def test_mcp_serves_the_job_result(job_app, github, database_url):
    client, _ = job_app
    result = wait_for_job(client, _start(client, github=LINK)["id"])["result"]
    served = from_store(database_url, result["repository"], result["snapshot"])
    try:
        overview = call(create_server(served), "graph_overview").structured_content
    finally:
        served.store.close()
    assert (overview["repository"], overview["snapshot"]) == (result["repository"], SHA)


def test_read_api_is_unchanged(job_app, github):
    client, _ = job_app
    result = wait_for_job(client, _start(client, github=LINK)["id"])["result"]
    listed = client.get("/api/v1/repositories")
    assert listed.content == b'{"repositories":[{"name":"github.com/o/ts-app","snapshots":["' + SHA.encode() + b'"]}]}'
    file = client.get("/api/v1/file", params={"repository": result["repository"], "snapshot": SHA, "path": "x"})
    assert file.status_code == 404 and file.json()["error"]["kind"] == "not_found"


def test_unknown_job(job_app):
    client, _ = job_app
    for job_id in ("0" * 32, "not-an-id"):
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 404
        assert response.json() == {"error": {"kind": "not_found", "message": f"job not found: {job_id}"}}
    assert client.get("/api/v1/jobs/" + "0" * 32, params={"x": "1"}).status_code == 400


def test_lower_limits_are_reported(job_app, github):
    github.serve("https://api.github.com/repos/o/ts-app/commits/main", body=SHA.encode())
    client, _ = job_app
    started = _start(client, github=LINK, ref="main", limits={"max_files": 100, "max_seconds": 2.5})
    assert started["limits"]["max_files"] == 100 and started["limits"]["max_seconds"] == 2.5
    assert started["source"]["ref"] == "main"
    assert wait_for_job(client, started["id"])["stage"] == "done"


def test_start_is_fast_while_a_job_runs(job_app, github):
    """SC-002: starting a job answers in under 1 s, whatever is running."""
    import threading
    import time

    release = threading.Event()
    tar = fixture_tarball("ts-app", SHA)

    def slow():
        release.wait(10)
        yield tar

    github.serve(f"https://codeload.github.com/o/ts-app/tar.gz/{SHA}", body=slow())
    client, _ = job_app
    first = _start(client, github=LINK)
    try:
        begin = time.monotonic()
        _start(client, github="https://github.com/o/other")
        assert time.monotonic() - begin < 1
    finally:
        release.set()
    wait_for_job(client, first["id"])
