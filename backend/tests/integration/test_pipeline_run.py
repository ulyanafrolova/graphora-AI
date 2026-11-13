"""`run_pipeline` gives what `analyze --store` stores, and reports its stages (specs/010 tasks T007)."""

import pytest

from archives import make_tar_gz
from conftest import FIXTURES, run_analyze
from graphora.ingest.source import GitHubSource, LocalSource, ZipSource
from graphora.ingest.walk import Deadline
from graphora.pipeline import PipelineLimits, run_pipeline
from jobs_helpers import fixture_zip

SHA = "0123456789abcdef0123456789abcdef01234567"
TAR = make_tar_gz(
    [
        ("o-r-0123456", "dir"),
        ("o-r-0123456/a.ts", "file", "import { b } from './b'\n"),
        ("o-r-0123456/b.ts", "file", "export const b = 1\n"),
    ],
    SHA,
)

pytestmark = pytest.mark.db


@pytest.fixture
def github(fake_gh):
    fake_gh.serve("https://api.github.com/repos/o/r/commits/HEAD", body=SHA.encode())
    fake_gh.serve(f"https://codeload.github.com/o/r/tar.gz/{SHA}", body=TAR)
    return fake_gh


def _run(source, store, workdir=None):
    stages = []
    result = run_pipeline(source, PipelineLimits(), store, Deadline(300), stages.append, workdir=workdir)
    return result, stages


def _cli_store(argument, database_url, monkeypatch):
    monkeypatch.setenv("GRAPHORA_DATABASE_URL", database_url)
    code, out, err = run_analyze(argument, "--store")
    assert code == 0, err
    return out


def test_local_folder(store, database_url, monkeypatch):
    result, stages = _run(LocalSource(FIXTURES / "py-flat" / "repo"), store)
    assert stages == ["fetching", "analyzing", "storing"]
    assert result.action == "stored" and result.fetched is None
    assert result.analysis.repository == "repo"
    assert _cli_store(FIXTURES / "py-flat" / "repo", database_url, monkeypatch) == result.analysis.graph


def test_zip(store, database_url, monkeypatch, tmp_path):
    archive = tmp_path / "app.zip"
    archive.write_bytes(fixture_zip("ts-app"))
    result, stages = _run(ZipSource(archive), store, workdir=tmp_path)
    assert stages == ["fetching", "analyzing", "storing"]
    assert result.fetched == "extracted app.zip"
    assert result.analysis.repository == "app"
    assert _cli_store(archive, database_url, monkeypatch) == result.analysis.graph
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app.zip"]


def test_github_then_reuse(store, github, database_url, monkeypatch):
    first, stages = _run(GitHubSource("o", "r", None), store)
    assert stages == ["resolving", "fetching", "analyzing", "storing"]
    assert (first.action, first.fetched) == ("stored", f"fetched github.com/o/r at {SHA}")
    assert first.analysis.snapshot == SHA

    second, stages = _run(GitHubSource("o", "r", None), store)
    assert stages == ["resolving"]
    assert (second.action, second.fetched) == ("reused", None)
    assert second.analysis.graph == first.analysis.graph
    assert len(github.urls("codeload.github.com")) == 1
    assert _cli_store("https://github.com/o/r", database_url, monkeypatch) == first.analysis.graph
