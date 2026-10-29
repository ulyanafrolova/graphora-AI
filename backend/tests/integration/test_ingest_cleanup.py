"""No temp folder outlives a run (specs/002-repo-ingest SC-004, FR-011; research.md § R11)."""

import tempfile

import pytest

from archives import make_tar_gz, make_zip
from conftest import run_analyze
from fake_github import FakeGitHub
from graphora import cli
from graphora.ingest import github

SHA = "0123456789abcdef0123456789abcdef01234567"
LINK = "https://github.com/o/r"
API = "https://api.github.com/repos/o/r/commits/HEAD"
TARBALL = f"https://codeload.github.com/o/r/tar.gz/{SHA}"
GOOD_TAR = make_tar_gz([("o-r-0123456", "dir"), ("o-r-0123456/a.py", "file", "x" * 100)], SHA)


@pytest.fixture
def tmp_dir(tmp_path, monkeypatch):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp))
    monkeypatch.setattr(tempfile, "tempdir", None)
    return tmp


@pytest.fixture
def fake(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(github, "_open", fake)
    return fake


def _leftovers(tmp):
    return sorted(p.name for p in tmp.iterdir() if p.name.startswith("graphora-"))


def _zip(tmp_path, data):
    path = tmp_path / "p.zip"
    path.write_bytes(data)
    return path


def test_github_success(tmp_dir, fake):
    fake.serve(API, body=SHA.encode())
    fake.serve(TARBALL, body=GOOD_TAR)
    assert run_analyze(LINK)[0] == 0
    assert _leftovers(tmp_dir) == []


def test_zip_success(tmp_dir, tmp_path):
    assert run_analyze(_zip(tmp_path, make_zip([("a.py", "file", "x")])))[0] == 0
    assert _leftovers(tmp_dir) == []


@pytest.mark.parametrize(
    "serve, args, status",
    [
        (lambda f: f.serve(API, status=404), (), 2),
        (lambda f: f.serve(API, status=403, headers={"x-ratelimit-remaining": "0"}), (), 5),
        (lambda f: (f.serve(API, body=SHA.encode()), f.serve(TARBALL, body="stall")), ("--max-seconds", "0.5"), 3),
        (lambda f: (f.serve(API, body=SHA.encode()), f.serve(TARBALL, body=GOOD_TAR)), ("--max-archive-bytes", "10"), 3),
        (lambda f: (f.serve(API, body=SHA.encode()), f.serve(TARBALL, body=GOOD_TAR)), ("--max-extract-bytes", "10"), 3),
        (
            lambda f: (f.serve(API, body=SHA.encode()), f.serve(TARBALL, body=make_tar_gz([("../x", "file", "x")]))),
            (),
            4,
        ),
    ],
)
def test_github_failures(tmp_dir, fake, serve, args, status):
    serve(fake)
    assert run_analyze(LINK, *args)[0] == status
    assert _leftovers(tmp_dir) == []


def test_invalid_zip(tmp_dir, tmp_path):
    assert run_analyze(_zip(tmp_path, b"PK\x03\x04garbage"))[0] == 4
    assert _leftovers(tmp_dir) == []


@pytest.mark.parametrize("source", ["github", "zip"])
def test_interrupt_inside_build(tmp_dir, tmp_path, fake, monkeypatch, source):
    def interrupted(*args, **kwargs):
        assert len(_leftovers(tmp_dir)) == 1  # the temp folder exists while build runs
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "build", interrupted)
    fake.serve(API, body=SHA.encode())
    fake.serve(TARBALL, body=GOOD_TAR)
    target = LINK if source == "github" else _zip(tmp_path, make_zip([("a.py", "file", "x")]))
    code, out, err = run_analyze(target)
    assert code == 130 and out == b""
    assert "graphora: error: interrupted" in err
    assert _leftovers(tmp_dir) == []
