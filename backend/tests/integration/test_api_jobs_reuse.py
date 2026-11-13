"""US2: a stored commit is not analyzed again; identical submissions share a job (specs/010 tasks T018)."""

import json
import threading
import time

import pytest

from jobs_helpers import fixture_tarball, stages_seen, wait_for_job

SHA = "2222222222222222222222222222222222222222"
LINK = "https://github.com/o/r"
API = "https://api.github.com/repos/o/r/commits/"
TARBALL = f"https://codeload.github.com/o/r/tar.gz/{SHA}"

pytestmark = pytest.mark.db


@pytest.fixture
def github(fake_gh):
    fake_gh.serve(API + "HEAD", body=SHA.encode())
    fake_gh.serve(TARBALL, body=fixture_tarball("py-flat", SHA))
    return fake_gh


def _start(client, **body):
    response = client.post("/api/v1/jobs", json=body)
    assert response.status_code == 202, response.text
    return json.loads(response.content)


def test_stored_commit_is_reused(job_app, github):
    client, _ = job_app
    first = wait_for_job(client, _start(client, github=LINK)["id"])
    assert first["result"]["action"] == "stored"

    begin = time.monotonic()
    second_id = _start(client, github=LINK)["id"]
    seen = stages_seen(client, second_id)
    assert time.monotonic() - begin < 2  # SC-003
    second = wait_for_job(client, second_id)
    assert second["result"] == {**first["result"], "action": "reused"}
    assert "fetching" not in seen
    assert github.urls("codeload.github.com") == [TARBALL]


def test_identical_submissions_share_one_job(job_app, github):
    client, _ = job_app
    release = threading.Event()
    tar = fixture_tarball("py-flat", SHA)

    def slow():
        release.wait(10)
        yield tar

    github.serve(TARBALL, body=slow())
    ids = {_start(client, github=LINK)["id"] for _ in range(10)}
    assert len(ids) == 1  # SC-004
    release.set()
    assert wait_for_job(client, ids.pop())["stage"] == "done"
    assert github.urls("codeload.github.com") == [TARBALL]


def test_stale_analysis_is_replaced(job_app, github, store):
    client, _ = job_app
    wait_for_job(client, _start(client, github=LINK)["id"])
    store._conn.execute("UPDATE analyses SET extractors = '{}'")
    again = wait_for_job(client, _start(client, github=LINK)["id"])
    assert again["result"]["action"] == "replaced"
    assert len(github.urls("codeload.github.com")) == 2


def test_two_refs_of_one_commit_store_once(job_app, github, store):
    client, _ = job_app
    github.serve(API + "main", body=SHA.encode())
    a = _start(client, github=LINK)
    b = _start(client, github=LINK, ref="main")
    assert a["id"] != b["id"]
    assert {wait_for_job(client, j["id"])["stage"] for j in (a, b)} == {"done"}
    assert store.list_repositories() == (("github.com/o/r", (SHA,)),)


def test_job_keeps_the_commit_it_resolved(job_app, github):
    client, _ = job_app
    release = threading.Event()
    tar = fixture_tarball("py-flat", SHA)

    def slow():
        release.wait(10)
        yield tar

    github.serve(TARBALL, body=slow())
    job_id = _start(client, github=LINK)["id"]
    while json.loads(client.get(f"/api/v1/jobs/{job_id}").content)["stage"] in ("queued", "resolving"):
        time.sleep(0.01)
    github.serve(API + "HEAD", body=b"3" * 40)  # a new commit is pushed while the job downloads
    release.set()
    assert wait_for_job(client, job_id)["result"]["snapshot"] == SHA
    assert github.urls("codeload.github.com") == [TARBALL]
