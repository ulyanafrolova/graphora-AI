"""A dulwich smart-HTTP server on 127.0.0.1 standing in for github.com (specs/014-hotspots research § R11).

The suite denies network access; `allow_loopback` lets connections to 127.0.0.1 through."""

from __future__ import annotations

import socket
import threading
from contextlib import contextmanager
from wsgiref.simple_server import WSGIRequestHandler, make_server

from dulwich.repo import Repo
from dulwich.server import DictBackend
from dulwich.web import make_wsgi_chain

_CONNECT = socket.socket.connect
_CREATE = socket.create_connection


def allow_loopback(monkeypatch) -> None:
    def connect(sock, address):
        if address[0] not in ("127.0.0.1", "localhost"):
            raise AssertionError("network access in tests")
        return _CONNECT(sock, address)

    def create(address, *args, **kwargs):
        if address[0] not in ("127.0.0.1", "localhost"):
            raise AssertionError("network access in tests")
        return _CREATE(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create)


class _Quiet(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def _failing(status: int):
    def app(environ, start_response):
        if status == 301:
            start_response("301 Moved Permanently", [("Location", "https://example.com/o/r.git/info/refs")])
        else:
            start_response(f"{status} Error", [("Content-Type", "text/plain")])
        return [b""]

    return app


@contextmanager
def serve_repo(path):
    """Serves the repository at `path` as `/o/r.git`; yields (url, state). `state["status"] = 500` breaks it."""
    repo = Repo(str(path))
    state: dict = {"status": None}
    app = make_wsgi_chain(DictBackend({b"/o/r.git": repo}))
    server = make_server(
        "127.0.0.1", 0, lambda e, s: (_failing(state["status"]) if state["status"] else app)(e, s), handler_class=_Quiet
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/o/r.git", state
    finally:
        server.shutdown()
        server.server_close()
        repo.close()
