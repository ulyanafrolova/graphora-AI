"""`graphora analyze` with the 002 sources (specs/002-repo-ingest/contracts/cli.md)."""

import pytest

from archives import make_tar_gz, make_zip
from conftest import FIXTURES, run_analyze
from fake_github import FakeGitHub
from graphora.ingest import github

FLAT = FIXTURES / "py-flat" / "repo"
SHA = "0123456789abcdef0123456789abcdef01234567"
LINK = "https://github.com/o/r"
API = "https://api.github.com/repos/o/r/commits/HEAD"
TARBALL = f"https://codeload.github.com/o/r/tar.gz/{SHA}"
GOOD_TAR = make_tar_gz([("o-r-0123456", "dir"), ("o-r-0123456/a.py", "file", "import os\n")], SHA)


def test_ref_with_folder_is_usage_error():
    code, out, err = run_analyze(FLAT, "--ref", "main")
    assert code == 2 and out == b""
    assert "--ref is allowed only with a GitHub link" in err


def test_missing_path_message(tmp_path):
    code, out, err = run_analyze(tmp_path / "nope")
    assert code == 2 and out == b""
    assert "not a directory or ZIP archive" in err


def test_default_ingest_limits_change_nothing():
    plain = run_analyze(FLAT)
    explicit = run_analyze(
        FLAT,
        "--max-archive-bytes", "209715200",
        "--max-extract-bytes", "209715200",
        "--max-entries", "20000",
    )
    assert plain[0] == explicit[0] == 0
    assert plain[1] == explicit[1]


# --- GitHub (T023) ------------------------------------------------------------------------------


@pytest.fixture
def fake(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(github, "_open", fake)
    return fake


def test_github_success(fake):
    fake.serve(API, body=SHA.encode())
    fake.serve(TARBALL, body=GOOD_TAR)
    code, out, err = run_analyze(LINK)
    assert code == 0, err
    assert f"graphora: info: fetched github.com/o/r at {SHA}" in err
    assert f'"snapshot": "{SHA}"'.encode() in out


def _serve_ok_api(fake):
    fake.serve(API, body=SHA.encode())


@pytest.mark.parametrize(
    "setup, args, status, text",
    [
        (lambda f: f.serve(API, status=404), (), 2, "repository not found or private"),
        (lambda f: f.serve(API.replace("HEAD", "nope"), status=422), ("--ref", "nope"), 2, "ref not found"),
        (lambda f: f.serve(API, status=409), (), 2, "repository is empty"),
        (lambda f: None, ("--ref", "a..b"), 2, "invalid ref name"),
        (
            lambda f: (_serve_ok_api(f), f.serve(TARBALL, headers={"Content-Length": "999999"}, body=b"")),
            ("--max-archive-bytes", "1000"),
            3,
            "archive size limit exceeded",
        ),
        (
            lambda f: (_serve_ok_api(f), f.serve(TARBALL, body="stall")),
            ("--max-seconds", "0.5"),
            3,
            "time limit exceeded",
        ),
        (
            lambda f: (_serve_ok_api(f), f.serve(TARBALL, body=make_tar_gz([("../x.py", "file", "x")]))),
            (),
            4,
            "unsafe archive entry ../x.py",
        ),
        (
            lambda f: f.serve(API, status=403, headers={"x-ratelimit-remaining": "0"}),
            (),
            5,
            "rate limit",
        ),
        (lambda f: f.serve(API, status=500), (), 5, "GitHub request failed"),
    ],
)
def test_github_failures_keep_out_untouched(fake, tmp_path, setup, args, status, text):
    setup(fake)
    out_file = tmp_path / "graph.json"
    out_file.write_bytes(b"old")
    code, out, err = run_analyze(LINK, "--out", str(out_file), *args)
    assert code == status, err
    assert text in err
    assert out == b""
    assert out_file.read_bytes() == b"old"


def test_bad_link_is_usage_error():
    code, out, err = run_analyze("https://github.com/o/r/blob/main/x.py")
    assert code == 2 and out == b""
    assert "not a GitHub repository link" in err


# --- ZIP (T030) ---------------------------------------------------------------------------------


def test_zip_success(tmp_path):
    path = tmp_path / "proj.zip"
    path.write_bytes(make_zip([("proj/a.py", "file", "import os\n")]))
    code, out, err = run_analyze(path)
    assert code == 0, err
    assert "graphora: info: extracted proj.zip" in err
    assert b'"snapshot": "content:' in out


def test_garbage_with_zip_signature_is_invalid_archive(tmp_path):
    path = tmp_path / "bad.zip"
    path.write_bytes(b"PK\x03\x04garbage")
    code, out, err = run_analyze(path)
    assert code == 4 and out == b""
    assert "invalid ZIP archive" in err


def test_zip_over_archive_limit(tmp_path):
    path = tmp_path / "big.zip"
    path.write_bytes(make_zip([("a.py", "file", "x" * 5000)]))
    code, out, err = run_analyze(path, "--max-archive-bytes", "100")
    assert code == 3 and out == b""
    assert "archive size limit exceeded" in err
