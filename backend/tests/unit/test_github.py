"""GitHub client against a fake (specs/002-repo-ingest research.md § R1–R3, R7)."""

import urllib.error
import urllib.request
from datetime import UTC, datetime

import pytest

from archives import make_tar_gz
from fake_github import FakeGitHub
from graphora.ingest import github
from graphora.ingest.errors import BadInput, RemoteError
from graphora.ingest.fetch import IngestLimits, fetch_snapshot
from graphora.ingest.source import GitHubSource
from graphora.ingest.walk import Deadline, LimitExceeded

SHA = "0123456789abcdef0123456789abcdef01234567"
API = "https://api.github.com/repos/o/r/commits/"
TARBALL = f"https://codeload.github.com/o/r/tar.gz/{SHA}"
SOURCE = GitHubSource("o", "r", None)


@pytest.fixture
def fake(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(github, "_open", fake)
    return fake


def test_resolve_default_branch(fake):
    fake.serve(API + "HEAD", body=SHA.encode())
    assert github.resolve_sha(SOURCE, Deadline(300)) == SHA
    (request,) = fake.requests
    assert request.headers["accept"] == "application/vnd.github.sha"
    assert request.headers["user-agent"].startswith("graphora")
    assert "authorization" not in request.headers


def test_resolve_ref_with_slash(fake):
    fake.serve(API + "feature/x", body=SHA.encode() + b"\n")
    assert github.resolve_sha(GitHubSource("o", "r", "feature/x"), Deadline(300)) == SHA


def test_body_not_a_sha(fake):
    fake.serve(API + "HEAD", body=b"<html>")
    with pytest.raises(RemoteError):
        github.resolve_sha(SOURCE, Deadline(300))


@pytest.mark.parametrize(
    "status, text", [(404, "github.com/o/r"), (422, "ref not found"), (409, "repository is empty")]
)
def test_bad_input_statuses(fake, status, text):
    fake.serve(API + "HEAD", status=status)
    with pytest.raises(BadInput) as exc:
        github.resolve_sha(SOURCE, Deadline(300))
    assert text in exc.value.message


def test_rate_limit_with_reset_time(fake):
    fake.serve(API + "HEAD", status=403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1793000000"})
    with pytest.raises(RemoteError) as exc:
        github.resolve_sha(SOURCE, Deadline(300))
    when = datetime.fromtimestamp(1793000000, UTC).strftime("%Y-%m-%d %H:%M")
    assert "rate limit" in exc.value.message and when in exc.value.message


def test_rate_limit_with_retry_after(fake):
    fake.serve(API + "HEAD", status=429, headers={"retry-after": "60"})
    with pytest.raises(RemoteError) as exc:
        github.resolve_sha(SOURCE, Deadline(300))
    assert "rate limit" in exc.value.message


def test_server_error(fake):
    fake.serve(API + "HEAD", status=500)
    with pytest.raises(RemoteError):
        github.resolve_sha(SOURCE, Deadline(300))


def test_connection_error(monkeypatch):
    def refuse(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(github, "_open", refuse)
    with pytest.raises(RemoteError) as exc:
        github.resolve_sha(SOURCE, Deadline(300))
    assert "connection refused" in exc.value.message


def test_redirect_status_is_remote_error(fake):
    fake.serve(API + "HEAD", status=302, headers={"Location": "https://evil.example/"})
    with pytest.raises(RemoteError):
        github.resolve_sha(SOURCE, Deadline(300))


def test_redirect_handler_allows_only_github():
    handler = github._GitHubRedirects()
    request = urllib.request.Request(TARBALL)
    with pytest.raises(RemoteError):
        handler.redirect_request(request, None, 302, "Found", {}, "https://evil.example/x")
    with pytest.raises(RemoteError):
        handler.redirect_request(request, None, 302, "Found", {}, "http://codeload.github.com/x")
    assert handler.redirect_request(request, None, 302, "Found", {}, "https://codeload.github.com/x") is not None


def test_tarball_url_and_content_length_limit(fake):
    fake.serve(TARBALL, headers={"Content-Length": "1000"}, body="stall")
    with pytest.raises(LimitExceeded) as exc:
        github.open_tarball(SOURCE, SHA, IngestLimits(max_archive_bytes=999), Deadline(300))
    assert exc.value.limit == "archive_bytes"
    assert fake.urls() == [TARBALL]


def test_stall_past_deadline_is_time_limit(fake):
    fake.serve(TARBALL, body="stall")
    stream = github.open_tarball(SOURCE, SHA, IngestLimits(), Deadline(0.5))
    with pytest.raises(LimitExceeded) as exc:
        stream.read(10)
    assert exc.value.limit == "seconds"


def test_stall_before_deadline_is_remote_error(fake, monkeypatch):
    monkeypatch.setattr(github, "_timeout", lambda deadline: 0.1)
    fake.serve(TARBALL, body="stall")
    stream = github.open_tarball(SOURCE, SHA, IngestLimits(), Deadline(300))
    with pytest.raises(RemoteError):
        stream.read(10)


def test_one_api_request_per_run(fake):
    fake.serve(API + "HEAD", body=SHA.encode())
    fake.serve(TARBALL, body=make_tar_gz([("o-r-0123456", "dir"), ("o-r-0123456/a.py", "file", "x")], SHA))
    with fetch_snapshot(SOURCE, IngestLimits(), Deadline(300)) as fetched:
        assert fetched.snapshot == SHA
        assert fetched.repository == "github.com/o/r"
        assert (fetched.root / "a.py").read_bytes() == b"x"
    assert fake.urls("api.github.com") == [API + "HEAD"]
    assert fake.urls("codeload.github.com") == [TARBALL]
