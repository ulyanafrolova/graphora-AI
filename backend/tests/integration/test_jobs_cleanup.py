"""The work folder: locked, emptied at start, no leftovers; stop and a full queue (specs/010 tasks T025)."""

import threading
import time

import pytest

from graphora.ingest.source import GitHubSource
from graphora.pipeline import PipelineLimits
from graphora.pipeline.jobs import JobRunner, QueueFull, Stopping, WorkDirInUse
from jobs_helpers import Stub


def _runner(work_dir, stub, **kwargs):
    runner = JobRunner(
        "postgresql://unused", PipelineLimits(), work_dir=work_dir, pipeline=stub, open_store=lambda url: None,
        **kwargs,
    )
    runner.start()
    return runner


def _wait(runner, job_id, stages):
    end = time.monotonic() + 10
    while runner.status(job_id).stage not in stages:
        assert time.monotonic() < end, runner.status(job_id).stage
        time.sleep(0.005)
    return runner.status(job_id)


def test_work_folder_is_locked(tmp_path):
    first = _runner(tmp_path / "jobs", Stub())
    try:
        with pytest.raises(WorkDirInUse):
            _runner(tmp_path / "jobs", Stub())
        other = _runner(tmp_path / "other", Stub())
        other.stop()
    finally:
        first.stop()
    again = _runner(tmp_path / "jobs", Stub())  # the lock is released by stop()
    again.stop()


def test_leftovers_are_removed_at_start(tmp_path):
    work = tmp_path / "jobs"
    (work / "dead-job" / "upload").mkdir(parents=True)
    (work / "dead-job" / "upload" / "a.zip").write_bytes(b"x")
    (work / "stray.tmp").write_bytes(b"x")
    outside = tmp_path / "keep.txt"
    outside.write_bytes(b"x")
    (work / "link").symlink_to(outside)
    runner = _runner(work, Stub())
    try:
        assert sorted(p.name for p in work.iterdir()) == [".lock"]
        assert outside.exists()  # a symlink is removed, never followed
    finally:
        runner.stop()


def test_stop_interrupts_running_and_queued_jobs(tmp_path):
    stub = Stub(block=True)  # loops on deadline.check() until released
    runner = _runner(tmp_path / "jobs", stub)
    running = runner.submit_github(GitHubSource("o", "a", None), PipelineLimits())
    queued = runner.submit_github(GitHubSource("o", "b", None), PipelineLimits())
    _wait(runner, running.id, ("storing",))
    runner.stop()
    interrupted = {"kind": "interrupted", "message": "the service is stopping"}
    assert runner.status(running.id).body["error"] == interrupted
    assert runner.status(queued.id).body["error"] == interrupted
    assert not [t for t in threading.enumerate() if t.name.startswith("graphora-job-")]
    assert [p.name for p in (tmp_path / "jobs").iterdir()] == [".lock"]
    with pytest.raises(Stopping):
        runner.submit_github(GitHubSource("o", "c", None), PipelineLimits())


def test_full_queue(tmp_path):
    stub = Stub(block=True)
    runner = _runner(tmp_path / "jobs", stub, queue_size=2)
    try:
        first = runner.submit_github(GitHubSource("o", "a", None), PipelineLimits())
        _wait(runner, first.id, ("storing",))
        runner.submit_github(GitHubSource("o", "b", None), PipelineLimits())
        runner.submit_github(GitHubSource("o", "c", None), PipelineLimits())
        with pytest.raises(QueueFull):
            runner.submit_github(GitHubSource("o", "d", None), PipelineLimits())
    finally:
        stub.release.set()
        runner.stop()


def test_full_queue_over_http(tmp_path):
    from fastapi.testclient import TestClient

    from graphora.api import create_app

    stub = Stub(block=True)
    runner = _runner(tmp_path / "jobs", stub, queue_size=1)
    client = TestClient(create_app(None, runner))
    try:
        first = client.post("/api/v1/jobs", json={"github": "https://github.com/o/a"}).json()
        _wait(runner, first["id"], ("storing",))
        assert client.post("/api/v1/jobs", json={"github": "https://github.com/o/b"}).status_code == 202
        full = client.post("/api/v1/jobs", json={"github": "https://github.com/o/c"})
        assert full.status_code == 429
        assert full.json()["error"] == {"kind": "too_many_jobs", "message": "too many jobs waiting: 1"}
        upload = client.post("/api/v1/jobs/zip", params={"name": "a.zip"}, content=b"PK\x05\x06" + b"\0" * 18)
        assert upload.status_code == 429
        assert [p.name for p in (tmp_path / "jobs").iterdir() if p.name != ".lock"] == [first["id"]]
    finally:
        stub.release.set()
        runner.stop()
    stopped = client.post("/api/v1/jobs", json={"github": "https://github.com/o/d"})
    assert stopped.status_code == 503
    assert stopped.json()["error"] == {"kind": "stopping", "message": "the service is stopping"}
