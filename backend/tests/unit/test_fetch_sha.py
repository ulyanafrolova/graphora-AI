"""`fetch_snapshot(..., sha=)` skips the ref lookup (005 contracts/store-api.md, research § R6)."""

from __future__ import annotations

import pytest

from archives import make_tar_gz
from fake_github import FakeGitHub
from graphora.ingest import github
from graphora.ingest.fetch import IngestLimits, fetch_snapshot
from graphora.ingest.source import GitHubSource, LocalSource, ZipSource
from graphora.ingest.walk import Deadline

SHA = "0123456789abcdef0123456789abcdef01234567"
API = "https://api.github.com/repos/o/r/commits/HEAD"
TARBALL = f"https://codeload.github.com/o/r/tar.gz/{SHA}"
TAR = make_tar_gz([("o-r-0123456", "dir"), ("o-r-0123456/a.py", "file", "import os\n")], SHA)


@pytest.fixture
def fake(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(github, "_open", fake)
    fake.serve(API, body=SHA.encode())
    fake.serve(TARBALL, body=TAR)
    return fake


def test_given_sha_skips_api(fake):
    with fetch_snapshot(GitHubSource("o", "r", None), IngestLimits(), Deadline(60), sha=SHA) as fetched:
        assert fetched.snapshot == SHA
        assert (fetched.root / "a.py").read_text() == "import os\n"
    assert fake.urls("api.github.com") == []
    assert fake.urls("codeload.github.com") == [TARBALL]


def test_no_sha_resolves(fake):
    with fetch_snapshot(GitHubSource("o", "r", None), IngestLimits(), Deadline(60)) as fetched:
        assert fetched.snapshot == SHA
    assert fake.urls("api.github.com") == [API]


@pytest.mark.parametrize("bad", ["abc", SHA.upper(), SHA + "0", ""])
def test_malformed_sha(fake, bad):
    with pytest.raises(ValueError, match="40 lower-case hex"):
        with fetch_snapshot(GitHubSource("o", "r", None), IngestLimits(), Deadline(60), sha=bad):
            pass
    assert fake.requests == []


def test_sha_with_other_sources(tmp_path):
    for source in (LocalSource(tmp_path), ZipSource(tmp_path / "x.zip")):
        with pytest.raises(ValueError, match="only for a GitHub source"):
            with fetch_snapshot(source, IngestLimits(), Deadline(60), sha=SHA):
                pass
