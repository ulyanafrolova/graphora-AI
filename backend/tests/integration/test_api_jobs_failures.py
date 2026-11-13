"""US4: failures are reported clearly and leave no trace (specs/010-end-to-end-pipeline tasks T024)."""

import json

import pytest

from archives import make_tar_gz
from graphora.store import InvalidAnalysis, Store, StoreUnavailable
from jobs_helpers import stages_seen, wait_for_job

pytestmark = pytest.mark.db

SHA = "4444444444444444444444444444444444444444"
LINK = "https://github.com/o/r"
API = "https://api.github.com/repos/o/r/commits/HEAD"
TARBALL = f"https://codeload.github.com/o/r/tar.gz/{SHA}"
TAR = make_tar_gz([("o-r-4444444", "dir"), ("o-r-4444444/a.py", "file", "import b\n"), ("o-r-4444444/b.py", "file", "")], SHA)


@pytest.fixture
def github(fake_gh):
    fake_gh.serve(API, body=SHA.encode())
    fake_gh.serve(TARBALL, body=TAR)
    return fake_gh


def _start(client, **body):
    response = client.post("/api/v1/jobs", json=body)
    assert response.status_code == 202, response.text
    return json.loads(response.content)["id"]


def _clean(store, runner):
    assert store.list_repositories() == ()
    assert [p.name for p in runner.work_dir.iterdir()] == [".lock"]


@pytest.mark.parametrize(
    "body,message",
    [
        ({"github": "/etc"}, "not a GitHub repository link: /etc"),
        ({"github": "app.zip"}, "not a GitHub repository link: app.zip"),
        (
            {"github": "https://gitlab.com/o/r"},
            "not a GitHub repository link: https://gitlab.com/o/r "
            "(accepted: https://github.com/<owner>/<repo>[.git][/] or .../tree/<ref>)",
        ),
        ({"github": LINK, "ref": "a..b"}, "invalid ref name: a..b"),
        ({"github": LINK + "/tree/x", "ref": "y"}, "ref given twice: in the link and as ref"),
        ({"github": LINK, "other": 1}, "unknown key: other"),
        ({}, "missing github: a GitHub repository link"),
    ],
)
def test_bad_input_creates_no_job(job_app, store, body, message):
    client, runner = job_app
    response = client.post("/api/v1/jobs", json=body)
    assert response.status_code == 400
    assert response.json()["error"] == {"kind": "bad_request", "message": message}
    _clean(store, runner)


def test_not_json(job_app):
    client, _ = job_app
    response = client.post("/api/v1/jobs", content=b"{", headers={"Content-Type": "application/json"})
    assert response.status_code == 400


def test_missing_repository_is_remote(job_app, store, fake_gh):
    client, runner = job_app
    fake_gh.serve(API, status=404)
    failed = wait_for_job(client, _start(client, github=LINK))
    assert (failed["stage"], failed["error"]["kind"]) == ("failed", "remote")
    assert failed["error"]["message"] == "repository not found or private: github.com/o/r"
    _clean(store, runner)


def test_limit(job_app, store, github):
    client, runner = job_app
    failed = wait_for_job(client, _start(client, github=LINK, limits={"max_files": 1}))
    assert failed["error"] == {"kind": "limit", "message": "file limit exceeded: at least 2 files > max_files 1"}
    _clean(store, runner)


@pytest.mark.parametrize("job_app", [{"database_url": "postgresql://u:hunter2@127.0.0.1:1/nope"}], indirect=True)
def test_store_unavailable_from_the_start(job_app, store, github):
    client, runner = job_app
    failed = wait_for_job(client, _start(client, github=LINK))
    assert failed["error"] == {"kind": "store", "message": "store unavailable"}
    _clean(store, runner)


def test_store_lost_while_storing(job_app, store, github, monkeypatch):
    client, runner = job_app
    stage_at_put = []

    def gone(self, repository, analysis):
        stage_at_put.extend(runner.status(j).stage for j in list(runner._jobs))
        raise StoreUnavailable("gone")

    monkeypatch.setattr(Store, "put", gone)
    job_id = _start(client, github=LINK)
    assert stages_seen(client, job_id)[-1] == "failed"
    assert stage_at_put == ["storing"]
    assert wait_for_job(client, job_id)["error"] == {"kind": "store", "message": "store unavailable"}
    _clean(store, runner)


def test_invalid_analysis(job_app, store, github, monkeypatch):
    def invalid(self, repository, analysis):
        raise InvalidAnalysis("x")

    monkeypatch.setattr(Store, "put", invalid)
    client, runner = job_app
    failed = wait_for_job(client, _start(client, github=LINK))
    assert failed["error"] == {"kind": "invalid", "message": "cannot store the analysis: x"}
    _clean(store, runner)


def test_unexpected_error_is_internal(job_app, store, github, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("/secret/server/path")

    monkeypatch.setattr("graphora.pipeline.run.analyze", broken)
    client, runner = job_app
    failed = wait_for_job(client, _start(client, github=LINK))
    assert failed["error"] == {"kind": "internal", "message": "internal error"}
    _clean(store, runner)


def test_nothing_else_changes_stored_data(job_app, store, github):
    client, _ = job_app
    job_id = _start(client, github=LINK)
    wait_for_job(client, job_id)
    before = store.list_repositories()
    calls = [
        ("delete", f"/api/v1/jobs/{job_id}"), ("put", f"/api/v1/jobs/{job_id}"),
        ("delete", "/api/v1/graph"), ("put", "/api/v1/graph"),
        ("delete", "/api/v1/repositories"), ("put", "/api/v1/repositories"),
        ("get", "/api/v1/jobs"), ("put", "/api/v1/jobs"), ("delete", "/api/v1/jobs"),
        ("put", "/api/v1/jobs/zip"), ("delete", "/api/v1/jobs/zip"),
    ]
    for method, path in calls:
        response = getattr(client, method)(path)
        assert response.status_code == 405, (method, path, response.status_code)
        assert response.json()["error"] == {"kind": "method_not_allowed", "message": "method not allowed"}
    assert client.get("/api/v1/jobs/zip").status_code == 404  # read as the job id "zip"
    assert store.list_repositories() == before
