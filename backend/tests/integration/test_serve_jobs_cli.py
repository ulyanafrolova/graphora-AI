"""`graphora serve` job options (specs/010-end-to-end-pipeline contracts/cli.md, tasks T026)."""

import pytest

from graphora import cli
from graphora.pipeline import PipelineLimits
from graphora.pipeline.jobs import JobRunner


@pytest.mark.parametrize("option", ["--workers", "--queue", "--max-files", "--max-seconds", "--max-entries"])
def test_values_below_one_are_usage_errors(option, capsys):
    assert cli.main(["serve", option, "0"]) == 2
    assert f"{option} must be at least 1" in capsys.readouterr().err


@pytest.fixture
def db(store, database_url, monkeypatch):
    monkeypatch.setenv("GRAPHORA_DATABASE_URL", database_url)
    return store


@pytest.mark.db
def test_runner_gets_the_options(db, monkeypatch, tmp_path):
    import uvicorn

    seen = []

    def run(app, **kwargs):
        seen.append(kwargs)
        assert {"/api/v1/jobs", "/api/v1/jobs/zip", "/api/v1/jobs/{job_id}"} <= set(app.openapi()["paths"])

    monkeypatch.setattr(uvicorn, "run", run)
    started = []
    real_start = JobRunner.start

    def start(self):
        started.append((self.workers, self.queue_size, self.work_dir, self.limits))
        real_start(self)

    monkeypatch.setattr(JobRunner, "start", start)
    work = tmp_path / "w"
    assert cli.main(["serve", "--workers", "2", "--queue", "5", "--work-dir", str(work), "--max-files", "10"]) == 0
    assert started == [(2, 5, work, PipelineLimits(max_files=10))]
    assert seen == [{"host": "127.0.0.1", "port": 8000}]
    assert [p.name for p in work.iterdir()] == [".lock"]


@pytest.mark.db
def test_locked_work_folder(db, monkeypatch, tmp_path, capsys):
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: None)
    holder = JobRunner("postgresql://unused", PipelineLimits(), work_dir=tmp_path / "w")
    holder.start()
    try:
        assert cli.main(["serve", "--work-dir", str(tmp_path / "w")]) == 2
        assert "work folder in use by another graphora serve: use --work-dir" in capsys.readouterr().err
    finally:
        holder.stop()


@pytest.mark.db
def test_work_folder_cannot_be_created(db, tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_bytes(b"x")
    assert cli.main(["serve", "--work-dir", str(blocker / "w")]) == 2
    assert "cannot create work folder" in capsys.readouterr().err
