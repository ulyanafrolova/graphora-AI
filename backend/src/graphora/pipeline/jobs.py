"""Background analysis jobs for `graphora serve` (specs/010-end-to-end-pipeline data-model.md, research § R1,
R3, R6–R8, R10, R11).

A `JobRunner` keeps every job of the running service in memory, a bounded FIFO queue of waiting jobs, and
`workers` threads that run `run_pipeline` on them. Each running job opens its own store connection and uses its
own folder inside the runner's work folder.
"""

from __future__ import annotations

import collections
import json
import logging
import secrets
import shutil
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from graphora.ingest.errors import InvalidArchive, RemoteError, UnsafeArchive
from graphora.ingest.source import GitHubSource, Source
from graphora.ingest.walk import Deadline, LimitExceeded
from graphora.pipeline.messages import limit_message
from graphora.pipeline.run import PipelineLimits, PipelineResult, run_pipeline

log = logging.getLogger("graphora.jobs")

STAGES = ("queued", "resolving", "fetching", "analyzing", "storing")
FINAL = ("done", "failed")


class QueueFull(Exception):
    def __init__(self, size: int) -> None:
        super().__init__(f"too many jobs waiting: {size}")
        self.size = size


class Stopping(Exception):
    """A submission after `stop()` began."""


class Interrupted(Exception):
    """Raised by a job's deadline when the runner is stopping."""


class WorkDirInUse(Exception):
    """Another service holds the work folder's lock."""


class JobDeadline(Deadline):
    """The job's time limit, which also stops the job when the runner stops (research § R7)."""

    def __init__(self, seconds: float, stop: threading.Event) -> None:
        super().__init__(seconds)
        self._stop = stop

    def check(self) -> None:
        if self._stop.is_set():
            raise Interrupted()
        super().check()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class JobStatus:
    """A consistent copy of a job's state; `to_json()` is the HTTP body (contracts/http-api.md)."""

    body: dict[str, Any]

    @property
    def id(self) -> str:
        return self.body["id"]

    @property
    def stage(self) -> str:
        return self.body["stage"]

    def to_json(self) -> bytes:
        return _json_bytes(self.body)


@dataclass
class _Job:
    id: str
    source: Source
    source_body: dict[str, Any]
    limits: PipelineLimits
    key: tuple[Any, ...] | None
    stage: str = "queued"
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    workdir: Path | None = field(default=None)

    def status(self) -> JobStatus:
        return JobStatus(
            {
                "id": self.id,
                "stage": self.stage,
                "source": dict(self.source_body),
                "limits": self.limits.as_dict(),
                "result": None if self.result is None else dict(self.result),
                "error": None if self.error is None else dict(self.error),
            }
        )


def _result(result: PipelineResult) -> dict[str, Any]:
    """The `done` body, with counts computed from the stored graph like the CLI summary (data-model.md)."""
    saved = result.analysis
    doc = json.loads(saved.graph)
    return {
        "repository": saved.repository,
        "snapshot": saved.snapshot,
        "action": result.action,
        "files": sum(1 for f in doc["coverage"]["files"] if f["status"] == "analyzed"),
        "edges": len(doc["edges"]),
        "unresolved": sum(1 for e in doc["edges"] if e["confidence"] == "unresolved"),
        "warnings": sorted(saved.warnings),
    }


def _error(exc: BaseException) -> dict[str, str]:
    """Exception → failure kind and message (research § R11). Messages never carry server paths or URLs."""
    from graphora.store import InvalidAnalysis, StoreUnavailable

    if isinstance(exc, RemoteError):
        return {"kind": "remote", "message": exc.message}
    if isinstance(exc, LimitExceeded):
        return {"kind": "limit", "message": limit_message(exc, "api")}
    if isinstance(exc, (UnsafeArchive, InvalidArchive)):
        return {"kind": "archive", "message": exc.message}
    if isinstance(exc, StoreUnavailable):
        log.warning("store unavailable: %s", exc.reason)
        return {"kind": "store", "message": "store unavailable"}
    if isinstance(exc, InvalidAnalysis):
        return {"kind": "invalid", "message": f"cannot store the analysis: {exc}"}
    if isinstance(exc, Interrupted):
        return {"kind": "interrupted", "message": "the service is stopping"}
    log.error("job failed", exc_info=exc)
    return {"kind": "internal", "message": "internal error"}


def _open_store(url: str):  # type: ignore[no-untyped-def]
    from graphora.store import Store

    return Store.open(url)


class JobRunner:
    def __init__(
        self,
        database_url: str,
        limits: PipelineLimits,
        workers: int = 1,
        queue_size: int = 20,
        work_dir: Path | None = None,
        pipeline: Callable[..., PipelineResult] = run_pipeline,
        open_store: Callable[[str], Any] = _open_store,
    ) -> None:
        if workers < 1 or queue_size < 1:
            raise ValueError("workers and queue_size must be at least 1")
        self.database_url = database_url
        self.limits = limits
        self.workers = workers
        self.queue_size = queue_size
        self.work_dir = work_dir if work_dir is not None else Path(tempfile.gettempdir()) / "graphora-jobs"
        self._pipeline = pipeline
        self._open_store = open_store
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._jobs: dict[str, _Job] = {}
        self._queue: collections.deque[str] = collections.deque()
        self._active: dict[tuple[Any, ...], str] = {}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # --- lifecycle -------------------------------------------------------------------------------------------

    def start(self) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        for n in range(self.workers):
            thread = threading.Thread(target=self._work, name=f"graphora-job-{n}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        with self._wake:
            self._stop.set()
            self._wake.notify_all()
        for thread in self._threads:
            thread.join()
        self._threads.clear()

    # --- submitting and reading ------------------------------------------------------------------------------

    def submit_github(self, source: GitHubSource, limits: PipelineLimits) -> JobStatus:
        key = ("github", source.owner, source.repo, source.ref or "", limits)
        body = {"kind": "github", "repository": f"github.com/{source.owner}/{source.repo}", "ref": source.ref}
        with self._wake:
            existing = self._active.get(key)
            if existing is not None:  # FR-011
                return self._jobs[existing].status()
            return self._enqueue(_Job(self._new_id(), source, body, limits, key))

    def status(self, job_id: str) -> JobStatus | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return None if job is None else job.status()

    def _new_id(self) -> str:
        while True:
            job_id = secrets.token_hex(16)
            if job_id not in self._jobs:
                return job_id

    def _enqueue(self, job: _Job) -> JobStatus:
        """Called with the lock held."""
        if self._stop.is_set():
            raise Stopping()
        if len(self._queue) >= self.queue_size:
            raise QueueFull(self.queue_size)
        self._jobs[job.id] = job
        if job.key is not None:
            self._active[job.key] = job.id
        self._queue.append(job.id)
        self._wake.notify()
        return job.status()

    # --- running ---------------------------------------------------------------------------------------------

    def _work(self) -> None:
        while True:
            with self._wake:
                while not self._queue and not self._stop.is_set():
                    self._wake.wait()
                if self._stop.is_set():
                    return
                job = self._jobs[self._queue.popleft()]
            self._run(job)

    def _set_stage(self, job: _Job, stage: str) -> None:
        with self._lock:
            if job.stage in STAGES and stage in STAGES and STAGES.index(stage) > STAGES.index(job.stage):
                job.stage = stage

    def _finish(self, job: _Job, result: dict[str, Any] | None, error: dict[str, str] | None) -> None:
        with self._lock:
            job.result, job.error = result, error
            job.stage = "done" if error is None else "failed"
            if job.key is not None and self._active.get(job.key) == job.id:
                del self._active[job.key]

    def _run(self, job: _Job) -> None:
        deadline = JobDeadline(job.limits.max_seconds, self._stop)  # FR-016: queue time does not count
        workdir = self.work_dir / job.id
        store = None
        try:
            workdir.mkdir(parents=True, exist_ok=True)
            store = self._open_store(self.database_url)
            outcome = self._pipeline(
                job.source, job.limits, store, deadline, lambda stage: self._set_stage(job, stage), workdir=workdir
            )
            self._finish(job, _result(outcome), None)
        except BaseException as exc:  # noqa: BLE001 — every failure becomes a status (FR-008)
            self._finish(job, None, _error(exc))
        finally:
            if store is not None:
                store.close()
            shutil.rmtree(workdir, ignore_errors=True)

