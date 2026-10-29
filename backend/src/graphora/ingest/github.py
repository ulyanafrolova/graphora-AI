"""Anonymous GitHub access: ref -> commit SHA, then the tarball of that SHA (specs/002-repo-ingest/research.md § R1–R3, R7)."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, BinaryIO
from urllib.parse import quote, urlsplit

from graphora.ingest.errors import BadInput, RemoteError
from graphora.ingest.source import GitHubSource
from graphora.ingest.walk import Deadline, LimitExceeded

if TYPE_CHECKING:
    from graphora.ingest.fetch import IngestLimits

_HOSTS = frozenset({"github.com", "api.github.com", "codeload.github.com"})
_SHA = re.compile(r"^[0-9a-f]{40}$")

try:
    USER_AGENT = f"graphora/{version('graphora')}"
except PackageNotFoundError:
    USER_AGENT = "graphora"


class _GitHubRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        target = urlsplit(newurl)
        if target.scheme != "https" or target.hostname not in _HOSTS:
            raise RemoteError(f"GitHub request failed: redirect to {target.hostname or newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_GitHubRedirects)


def _open(request: urllib.request.Request, timeout: float):  # type: ignore[no-untyped-def]
    """Replaced by a fake in tests."""
    return _opener.open(request, timeout=timeout)


def _timeout(deadline: Deadline) -> float:
    return max(0.1, deadline.remaining())


def _network_error(host: str, exc: BaseException, deadline: Deadline) -> Exception:
    if deadline.remaining() <= 0:
        try:
            deadline.check()
        except LimitExceeded as limit:
            return limit
    reason = getattr(exc, "reason", None) or exc
    return RemoteError(f"GitHub request failed: {host} {reason}")


def _rate_limit_time(headers) -> str | None:  # type: ignore[no-untyped-def]
    reset, retry = headers.get("x-ratelimit-reset"), headers.get("retry-after")
    if reset and reset.isdigit():
        when = datetime.fromtimestamp(int(reset), UTC)
    elif retry and retry.isdigit():
        when = datetime.now(UTC) + timedelta(seconds=int(retry))
    else:
        return None
    return when.strftime("%Y-%m-%d %H:%M")


def _status_error(exc: urllib.error.HTTPError, source: GitHubSource, host: str) -> Exception:
    repository = f"github.com/{source.owner}/{source.repo}"
    headers = exc.headers
    if exc.code == 404:
        return BadInput(f"repository not found or private: {repository}")
    if exc.code == 422:
        return BadInput(f"ref not found or ambiguous in {repository}: {source.ref or 'HEAD'}")
    if exc.code == 409:
        return BadInput(f"repository is empty: {repository}")
    if exc.code in (403, 429) and (headers.get("x-ratelimit-remaining") == "0" or headers.get("retry-after")):
        when = _rate_limit_time(headers)
        return RemoteError("GitHub API rate limit reached" + (f"; retry after {when} UTC" if when else ""))
    return RemoteError(f"GitHub request failed: {host} {exc.code}")


def _request(url: str, source: GitHubSource, deadline: Deadline, **headers: str):  # type: ignore[no-untyped-def]
    host = urlsplit(url).hostname or url
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    try:
        return _open(request, _timeout(deadline))
    except urllib.error.HTTPError as exc:
        raise _status_error(exc, source, host) from None
    except (urllib.error.URLError, OSError) as exc:
        raise _network_error(host, exc, deadline) from None


def resolve_sha(source: GitHubSource, deadline: Deadline) -> str:
    ref = quote(source.ref, safe="/") if source.ref else "HEAD"
    url = f"https://api.github.com/repos/{source.owner}/{source.repo}/commits/{ref}"
    response = _request(url, source, deadline, Accept="application/vnd.github.sha")
    try:
        body = response.read(100)
    except OSError as exc:
        raise _network_error("api.github.com", exc, deadline) from None
    finally:
        response.close()
    sha = body.decode("ascii", "replace").strip()
    if not _SHA.match(sha):
        raise RemoteError("GitHub request failed: api.github.com returned no commit SHA")
    return sha


class _Download:
    """The tarball response: counts bytes and turns timeouts into the deadline or a remote error."""

    def __init__(self, response, limit: int, deadline: Deadline) -> None:  # type: ignore[no-untyped-def]
        self._response = response
        self._limit = limit
        self._deadline = deadline
        self._read = 0

    def read(self, n: int = -1) -> bytes:
        try:
            data = self._response.read(n)
        except OSError as exc:
            raise _network_error("codeload.github.com", exc, self._deadline) from None
        self._read += len(data)
        if self._read > self._limit:
            raise LimitExceeded("archive_bytes", self._limit, self._read)
        return data

    def close(self) -> None:
        self._response.close()


def open_tarball(source: GitHubSource, sha: str, limits: IngestLimits, deadline: Deadline) -> BinaryIO:
    url = f"https://codeload.github.com/{source.owner}/{source.repo}/tar.gz/{sha}"
    response = _request(url, source, deadline)
    length = response.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > limits.max_archive_bytes:
        response.close()
        raise LimitExceeded("archive_bytes", limits.max_archive_bytes, int(length))
    return _Download(response, limits.max_archive_bytes, deadline)  # type: ignore[return-value]
