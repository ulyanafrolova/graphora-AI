"""Helpers for the 010 job tests (specs/010-end-to-end-pipeline tasks T001)."""

from __future__ import annotations

import json
import threading
import time

import pytest

from archives import tar_of_dir, zip_of_dir
from conftest import FIXTURES
from graphora.ingest.source import GitHubSource
from graphora.pipeline import PipelineResult
from graphora.store import StoredAnalysis

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


# --- a stub pipeline for JobRunner tests without a database --------------------------------------------------

GRAPH = json.dumps(
    {
        "snapshot": "0" * 40,
        "coverage": {"files": [{"status": "analyzed"}, {"status": "analyzed"}, {"status": "not_code"}]},
        "edges": [{"confidence": "resolved"}, {"confidence": "unresolved"}],
    }
).encode()
STORED = StoredAnalysis("github.com/o/r", "0" * 40, 1, {}, ("b.json", "a.json"), GRAPH)
SRC = GitHubSource("o", "r", "main")


class Stub:
    """A pipeline that reports the given stages, then waits for `release` (if set) and returns."""

    def __init__(self, stages=("resolving", "fetching", "analyzing", "storing"), block=False, error=None):
        self.stages = stages
        self.release = threading.Event()
        if not block:
            self.release.set()
        self.started = []
        self.error = error

    def __call__(self, source, limits, store, deadline, on_stage, workdir=None):
        self.started.append(source)
        for stage in self.stages:
            on_stage(stage)
        while not self.release.wait(0.01):
            deadline.check()
        if self.error is not None:
            raise self.error
        return PipelineResult(STORED, "stored", None)
