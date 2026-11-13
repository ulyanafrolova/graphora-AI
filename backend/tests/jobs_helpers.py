"""Helpers for the 010 job tests (specs/010-end-to-end-pipeline tasks T001)."""

from __future__ import annotations

import json
import time

import pytest

from archives import tar_of_dir, zip_of_dir
from conftest import FIXTURES

FINAL = ("done", "failed")


def _get(client, job_id: str) -> dict:
    response = client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200, response.text
    return json.loads(response.content)


def stages_seen(client, job_id: str, timeout: float = 30.0) -> list[str]:
    """Every distinct stage in the order seen, ending with `done` or `failed`."""
    seen: list[str] = []
    end = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < end:
        body = _get(client, job_id)
        if not seen or seen[-1] != body["stage"]:
            seen.append(body["stage"])
        if body["stage"] in FINAL:
            return seen
        time.sleep(0.02)
    pytest.fail(f"job {job_id} did not finish in {timeout}s: {body}")


def wait_for_job(client, job_id: str, timeout: float = 30.0) -> dict:
    stages_seen(client, job_id, timeout)
    return _get(client, job_id)


def fixture_tarball(name: str, sha: str) -> bytes:
    """The tarball GitHub serves for a fixture repository at `sha`."""
    return tar_of_dir(FIXTURES / name / "repo", prefix=f"o-{name}-{sha[:7]}", pax_comment=sha, exclude={".git"})


def fixture_zip(name: str) -> bytes:
    return zip_of_dir(FIXTURES / name / "repo")
