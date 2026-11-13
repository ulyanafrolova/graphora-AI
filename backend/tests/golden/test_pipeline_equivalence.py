"""Every fixture through HTTP — as a GitHub link and as a ZIP upload — stores the graph `graphora analyze` prints,
on each of 3 runs (specs/010-end-to-end-pipeline SC-001, constitution VIII; tasks T031).

The reference is a plain `graphora analyze` run: 005 SC-001 shows it equals what `--store` stores, and an
`--store` run after a job would only reuse the job's bytes."""

import json

import pytest

from conftest import FIXTURES, run_analyze
from jobs_helpers import fixture_tarball, fixture_zip, wait_for_job

FIXTURE_NAMES = sorted(p.name for p in FIXTURES.iterdir() if (p / "repo").is_dir())
SHA = "5555555555555555555555555555555555555555"

pytestmark = pytest.mark.db


def _graph(client, result):
    response = client.get("/api/v1/graph", params={"repository": result["repository"], "snapshot": result["snapshot"]})
    assert response.status_code == 200
    return response.content


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_http_equals_cli(name, job_app, store, fake_gh, tmp_path):
    client, _ = job_app
    link = f"https://github.com/o/{name}"
    fake_gh.serve(f"https://api.github.com/repos/o/{name}/commits/HEAD", body=SHA.encode())
    fake_gh.serve(f"https://codeload.github.com/o/{name}/tar.gz/{SHA}", body=fixture_tarball(name, SHA))
    data = fixture_zip(name)
    archive = tmp_path / f"{name}.zip"
    archive.write_bytes(data)

    code, cli_link, err = run_analyze(link)
    assert code == 0, err
    code, cli_zip, err = run_analyze(archive)
    assert code == 0, err

    runs = []
    for _ in range(3):
        store._conn.execute("TRUNCATE files, analyses, blobs")
        started = client.post("/api/v1/jobs", json={"github": link}).json()
        uploaded = json.loads(
            client.post("/api/v1/jobs/zip", params={"name": f"{name}.zip"}, content=data).content
        )
        done = [wait_for_job(client, job["id"]) for job in (started, uploaded)]
        assert [d["stage"] for d in done] == ["done", "done"], done
        assert [d["result"]["action"] for d in done] == ["stored", "stored"]
        runs.append(tuple(_graph(client, d["result"]) for d in done))
    assert runs[0] == (cli_link, cli_zip)
    assert runs[1] == runs[0] and runs[2] == runs[0]
