"""JobRunner with a stub pipeline: no database, no network (specs/010-end-to-end-pipeline tasks T010, T017)."""

import json
import re
import threading
import time

import pytest

from graphora.ingest.source import GitHubSource
from graphora.pipeline import PipelineLimits, PipelineResult
from graphora.pipeline.jobs import JobRunner
from graphora.store import StoredAnalysis

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


@pytest.fixture
def make_runner(tmp_path):
    runners = []

    def make(stub, **kwargs):
        runner = JobRunner(
            "postgresql://unused", PipelineLimits(), work_dir=tmp_path / "jobs", pipeline=stub,
            open_store=lambda url: None, **kwargs,
        )
        runner.start()
        runners.append(runner)
        return runner

    yield make
    for runner in runners:
        runner.stop()


def wait(runner, job_id, stages=("done", "failed"), timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        status = runner.status(job_id)
        if status.stage in stages:
            return status
        time.sleep(0.005)
    pytest.fail(f"job did not reach {stages}: {runner.status(job_id).stage}")


def body(status):
    return json.loads(status.to_json())


def test_submit_returns_a_queued_job_with_a_random_id(make_runner):
    stub = Stub(block=True)
    runner = make_runner(stub)
    first = runner.submit_github(SRC, PipelineLimits())
    assert re.fullmatch(r"[0-9a-f]{32}", first.id)
    ids = {first.id} | {runner.submit_github(GitHubSource("o", f"r{i}", None), PipelineLimits()).id for i in range(15)}
    assert len(ids) == 16
    stub.release.set()


def test_one_worker_runs_jobs_in_order(make_runner):
    stub = Stub(block=True)
    runner = make_runner(stub)
    a = runner.submit_github(GitHubSource("o", "a", None), PipelineLimits())
    b = runner.submit_github(GitHubSource("o", "b", None), PipelineLimits())
    wait(runner, a.id, ("storing",))
    assert runner.status(b.id).stage == "queued"
    stub.release.set()
    wait(runner, b.id)
    assert [s.repo for s in stub.started] == ["a", "b"]


def test_done_has_result_and_counts(make_runner):
    runner = make_runner(Stub())
    job = runner.submit_github(SRC, PipelineLimits())
    done = body(wait(runner, job.id))
    assert done["stage"] == "done" and done["error"] is None
    assert done["result"] == {
        "action": "stored", "edges": 2, "files": 2, "repository": "github.com/o/r", "snapshot": "0" * 40,
        "unresolved": 1, "warnings": ["a.json", "b.json"],
    }
    assert done["source"] == {"kind": "github", "ref": "main", "repository": "github.com/o/r"}
    assert done["limits"] == PipelineLimits().as_dict()


def test_failed_has_error_only(make_runner):
    runner = make_runner(Stub(error=RuntimeError("secret /server/path")))
    failed = body(wait(runner, runner.submit_github(SRC, PipelineLimits()).id))
    assert failed["stage"] == "failed" and failed["result"] is None
    assert failed["error"] == {"kind": "internal", "message": "internal error"}


def test_stages_never_move_back(make_runner):
    runner = make_runner(Stub(stages=("fetching", "resolving", "analyzing"), block=True))
    job = runner.submit_github(SRC, PipelineLimits())
    assert wait(runner, job.id, ("analyzing",)).stage == "analyzing"
    runner._pipeline.release.set()
    wait(runner, job.id)


def test_status_bytes_are_stable(make_runner):
    runner = make_runner(Stub())
    job = runner.submit_github(SRC, PipelineLimits())
    wait(runner, job.id)
    first = runner.status(job.id).to_json()
    assert all(runner.status(job.id).to_json() == first for _ in range(5))
    assert b" " not in first.replace(b"github.com/o/r", b"")
    text = first.decode()
    assert list(json.loads(text)) == sorted(json.loads(text))
    assert not re.search(r"\d{4}-\d{2}-\d{2}|time|elapsed|position", text)


def test_unknown_ids(make_runner):
    runner = make_runner(Stub())
    assert runner.status("nope") is None
    assert runner.status("0" * 32) is None


def test_finished_jobs_stay_readable(make_runner):
    runner = make_runner(Stub())
    first = runner.submit_github(SRC, PipelineLimits())
    wait(runner, first.id)
    for i in range(5):
        wait(runner, runner.submit_github(GitHubSource("o", f"x{i}", None), PipelineLimits()).id)
    assert runner.status(first.id).stage == "done"  # FR-012


# --- US2: identical unfinished submissions share one job (research § R10) ----------------------------------


def test_identical_unfinished_submission_returns_the_same_job(make_runner):
    stub = Stub(block=True)
    runner = make_runner(stub)
    first = runner.submit_github(SRC, PipelineLimits())
    assert runner.submit_github(GitHubSource("o", "r", "main"), PipelineLimits()).id == first.id
    assert runner.submit_github(GitHubSource("o", "r", "dev"), PipelineLimits()).id != first.id
    assert runner.submit_github(SRC, PipelineLimits(max_files=10)).id != first.id
    stub.release.set()
    wait(runner, first.id)
    assert runner.submit_github(SRC, PipelineLimits()).id != first.id
