"""US3: upload a ZIP archive over HTTP (specs/010-end-to-end-pipeline tasks T021)."""

import json
import os

import pytest

from archives import bomb_zip, make_zip
from conftest import run_analyze
from jobs_helpers import fixture_zip, wait_for_job

pytestmark = pytest.mark.db

HOSTILE = [
    ("traversal", make_zip([("a/../../x.py", "file", "x")]), "archive", "a/../../x.py"),
    ("absolute", make_zip([("/etc/x", "file", "x")]), "archive", "/etc/x"),
    ("under symlink", make_zip([("l", "symlink", "/tmp"), ("l/inner.py", "file", "x")]), "archive", "l/inner.py"),
    ("bomb", bomb_zip(2 * 1024 * 1024), "limit", "max_extract_bytes"),
]


def _upload(client, name, data, **params):
    return client.post("/api/v1/jobs/zip", params={"name": name, **params}, content=data,
                       headers={"Content-Type": "application/zip"})


def _job_dirs(runner):
    return sorted(p.name for p in runner.work_dir.iterdir() if p.name != ".lock")


def test_upload_equals_cli(job_app, tmp_path, database_url, monkeypatch):
    client, runner = job_app
    data = fixture_zip("py-flat")
    response = _upload(client, "app.zip", data)
    assert response.status_code == 202, response.text
    started = json.loads(response.content)
    assert started["source"] == {"kind": "zip", "name": "app.zip", "repository": "app"}
    done = wait_for_job(client, started["id"])
    assert done["stage"] == "done", done

    archive = tmp_path / "app.zip"
    archive.write_bytes(data)
    monkeypatch.setenv("GRAPHORA_DATABASE_URL", database_url)
    code, out, err = run_analyze(archive, "--store")
    assert code == 0, err
    result = done["result"]
    assert result["repository"] == "app" and result["snapshot"].startswith("content:")
    graph = client.get("/api/v1/graph", params={"repository": "app", "snapshot": result["snapshot"]})
    assert graph.content == out
    assert _job_dirs(runner) == []


def test_upload_over_the_limit_stops_at_once(job_app):
    client, runner = job_app
    data = fixture_zip("py-flat")

    def chunks():
        yield data[:100]
        yield data[100:]

    response = _upload(client, "app.zip", chunks(), max_archive_bytes="100")
    assert response.status_code == 413
    assert response.json()["error"]["kind"] == "limit"
    assert response.json()["error"]["message"].endswith("bytes > max_archive_bytes 100")
    assert _job_dirs(runner) == []

    declared = _upload(client, "app.zip", data, max_archive_bytes="100")
    assert declared.status_code == 413
    assert declared.json()["error"]["message"] == (
        f"archive size limit exceeded: at least {len(data)} bytes > max_archive_bytes 100"
    )


@pytest.mark.parametrize("case,data,kind,needle", HOSTILE, ids=[h[0] for h in HOSTILE])
def test_hostile_archives_fail_like_the_cli(job_app, tmp_path, case, data, kind, needle):
    client, runner = job_app
    before = set(os.listdir(tmp_path))
    params = {"max_extract_bytes": str(1024 * 1024)} if case == "bomb" else {}
    response = _upload(client, "evil.zip", data, **params)
    assert response.status_code == 202, response.text
    failed = wait_for_job(client, response.json()["id"])
    assert (failed["stage"], failed["error"]["kind"]) == ("failed", kind)
    assert needle in failed["error"]["message"]

    archive = tmp_path / "evil.zip"
    archive.write_bytes(data)
    cli_args = ["--max-extract-bytes", str(1024 * 1024)] if case == "bomb" else []
    _, _, err = run_analyze(archive, *cli_args)
    cli_reason = err.strip().splitlines()[-1].removeprefix("graphora: error: ")
    assert failed["error"]["message"] == cli_reason.replace("--max-extract-bytes", "max_extract_bytes")
    assert set(os.listdir(tmp_path)) - before == {"evil.zip"}  # SC-006: nothing outside the job folder
    assert _job_dirs(runner) == []


def test_same_archive_twice_is_stored_once(job_app, store):
    client, _ = job_app
    data = fixture_zip("ts-app")
    jobs = [_upload(client, "same.zip", data).json()["id"] for _ in range(2)]
    results = [wait_for_job(client, j)["result"] for j in jobs]
    assert {r["action"] for r in results} == {"stored", "reused"}
    assert store.list_repositories() == (("same", (results[0]["snapshot"],)),)


@pytest.mark.parametrize("data", [b"", b"not a zip at all"])
def test_not_a_zip_is_rejected(job_app, data):
    client, runner = job_app
    response = _upload(client, "x.zip", data)
    assert response.status_code == 400
    assert response.json()["error"] == {"kind": "bad_request", "message": "not a ZIP archive: x.zip"}
    assert _job_dirs(runner) == []


def test_bad_name_is_rejected(job_app):
    client, _ = job_app
    assert _upload(client, "../x.zip", b"PK\x05\x06").status_code == 400
    assert client.post("/api/v1/jobs/zip", content=b"PK").status_code == 400  # no name
