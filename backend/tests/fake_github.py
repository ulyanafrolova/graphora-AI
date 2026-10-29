"""Fake GitHub that replaces `graphora.ingest.github._open` in tests (specs/002-repo-ingest/research.md § R10).

`body` is bytes, an iterator of chunks, or "stall" (read blocks for the timeout, then raises TimeoutError).
"""

from __future__ import annotations

import io
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from email.message import Message

Body = bytes | Iterable[bytes] | str


@dataclass(frozen=True)
class RecordedRequest:
    url: str
    headers: dict[str, str]  # lower-case keys
    timeout: float


def _headers(values: Mapping[str, str]) -> Message:
    message = Message()
    for key, value in values.items():
        message[key] = value
    return message


class FakeResponse(io.RawIOBase):
    def __init__(self, url: str, status: int, headers: Mapping[str, str], body: Body, timeout: float) -> None:
        self.url = url
        self.status = status
        self.headers = _headers(headers)
        self._timeout = timeout
        self._stall = body == "stall"
        self._chunks: Iterator[bytes]
        if isinstance(body, bytes):
            self._chunks = iter([body])
        elif isinstance(body, str):
            self._chunks = iter([])
        else:
            self._chunks = iter(body)
        self._pending = b""

    def readable(self) -> bool:
        return True

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url

    def read(self, n: int = -1) -> bytes:
        if self._stall:
            time.sleep(self._timeout)
            raise TimeoutError("timed out")
        if n is None or n < 0:
            data = self._pending + b"".join(self._chunks)
            self._pending = b""
            return data
        if not self._pending:
            self._pending = next(self._chunks, b"")
        data, self._pending = self._pending[:n], self._pending[n:]
        return data


class FakeGitHub:
    """Called as `opener(request, timeout)`. Like urllib, a status of 300 or above raises HTTPError."""

    def __init__(self) -> None:
        self.responses: dict[str, tuple[int, dict[str, str], Body]] = {}
        self.requests: list[RecordedRequest] = []

    def serve(self, url: str, status: int = 200, headers: Mapping[str, str] | None = None, body: Body = b"") -> None:
        self.responses[url] = (status, dict(headers or {}), body)

    def __call__(self, request: urllib.request.Request | str, timeout: float) -> FakeResponse:
        if isinstance(request, str):
            request = urllib.request.Request(request)
        url = request.full_url
        self.requests.append(RecordedRequest(url, {k.lower(): v for k, v in request.header_items()}, timeout))
        if url not in self.responses:
            raise AssertionError(f"unexpected request: {url}")
        status, headers, body = self.responses[url]
        if status >= 300:
            content = body if isinstance(body, bytes) else b""
            raise urllib.error.HTTPError(url, status, f"HTTP {status}", _headers(headers), io.BytesIO(content))
        return FakeResponse(url, status, headers, body, timeout)

    def urls(self, host: str | None = None) -> list[str]:
        prefix = f"https://{host}/" if host else ""
        return [r.url for r in self.requests if r.url.startswith(prefix)]
