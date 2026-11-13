"""`fetch_snapshot(..., workdir=...)` keeps its temp folder inside `workdir` (specs/010 research § R8)."""

import tempfile
from pathlib import Path

import pytest

from archives import make_tar_gz, make_zip
from graphora.ingest.fetch import IngestLimits, fetch_snapshot
from graphora.ingest.source import GitHubSource, ZipSource
from graphora.ingest.walk import Deadline

SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def archive(tmp_path):
    path = tmp_path / "app.zip"
    path.write_bytes(make_zip([("a.py", "file", "import b\n"), ("b.py", "file", "")]))
    return path


def test_zip_inside_workdir(archive, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    with fetch_snapshot(ZipSource(archive), IngestLimits(), Deadline(60), workdir=work) as fetched:
        assert work in fetched.root.parents
        assert (fetched.root / "a.py").is_file()
    assert list(work.iterdir()) == []


def test_removed_when_block_raises(archive, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(RuntimeError):
        with fetch_snapshot(ZipSource(archive), IngestLimits(), Deadline(60), workdir=work):
            raise RuntimeError("boom")
    assert list(work.iterdir()) == []


def test_github_inside_workdir(fake_gh, tmp_path):
    fake_gh.serve(
        f"https://codeload.github.com/o/r/tar.gz/{SHA}",
        body=make_tar_gz([("o-r-0123456", "dir"), ("o-r-0123456/a.py", "file", "")], SHA),
    )
    work = tmp_path / "work"
    work.mkdir()
    with fetch_snapshot(GitHubSource("o", "r", None), IngestLimits(), Deadline(60), sha=SHA, workdir=work) as fetched:
        assert work in fetched.root.parents
    assert list(work.iterdir()) == []


def test_default_is_system_temp(archive):
    with fetch_snapshot(ZipSource(archive), IngestLimits(), Deadline(60)) as fetched:
        assert Path(tempfile.gettempdir()).resolve() in fetched.root.resolve().parents
