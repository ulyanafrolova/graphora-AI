"""GitHub history: commits and trees fetched over git's smart HTTP into a temp repository (specs/014-hotspots
research § R5). A dulwich server on 127.0.0.1 stands in for github.com; it ignores `deepen-since`."""

import json
import threading
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest
from dulwich.repo import Repo
from dulwich.server import DictBackend
from dulwich.web import make_wsgi_chain

from archives import tar_of_dir
from conftest import run_analyze
from fake_github import FakeGitHub
from graphora.history import github as history_github
from graphora.history.reader import read_history
from graphora.ingest import github
from graphora.ingest.source import GitHubSource
from graphora.ingest.walk import Deadline
from history_repos import make_repo

SOURCE = GitHubSource("o", "r", None)
COMMITS = [
    {"files": {"a.py": b"import b\n", "b.py": b"x = 1\n"}, "author": "A <a@example.com>"},
    {"files": {"b.py": b"x = 2\n"}, "author": "B <b@example.com>"},
    {"files": {"b.py": b"x = 3\n", "c.py": b"import b\n"}, "author": "A <a@example.com>"},
]


class _Quiet(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def _broken(app, status):
    def wrapped(environ, start_response):
        if status == 301:
            start_response("301 Moved Permanently", [("Location", "https://example.com/o/r.git/info/refs")])
        else:
            start_response("500 Internal Server Error", [("Content-Type", "text/plain")])
        return [b""]

    return wrapped if status else app


@pytest.fixture
def served(tmp_path, monkeypatch):
    """Serves a built repository; `served.status = 500 | 301` makes the server fail."""
    origin = tmp_path / "origin"
    shas = make_repo(origin, COMMITS)
    repo = Repo(str(origin))
    state = {"status": None}
    app = make_wsgi_chain(DictBackend({b"/o/r.git": repo}))
    server = make_server("127.0.0.1", 0, lambda e, s: _broken(app, state["status"])(e, s), handler_class=_Quiet)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(history_github, "_remote_url", lambda source: f"http://127.0.0.1:{server.server_port}/o/r.git")
    yield origin, shas, state
    server.shutdown()
    repo.close()


def fetch(tmp_path, sha, max_bytes=10**8, deadline=None):
    return history_github.fetch_history(SOURCE, sha, tmp_path / "work", max_bytes, deadline or Deadline(60))


def test_fetch_equals_local(served, tmp_path):
    origin, shas, _ = served
    fetched = fetch(tmp_path, shas[-1])
    assert not isinstance(fetched, str), fetched
    repo, shallow = fetched
    paths = frozenset({"a.py", "b.py", "c.py"})
    try:
        remote = read_history(repo.object_store, shas[-1], paths, shallow, Deadline(60))
    finally:
        repo.close()
    local_repo = Repo(str(origin))
    try:
        local = read_history(local_repo.object_store, shas[-1], paths, frozenset(), Deadline(60))
    finally:
        local_repo.close()
    assert remote == local
    assert remote.files[1].path == "b.py" and (remote.files[1].commits, remote.files[1].authors) == (3, 2)
    assert (tmp_path / "work").is_dir()


def test_too_large(served, tmp_path):
    _, shas, _ = served
    assert fetch(tmp_path, shas[-1], max_bytes=100) == "too_large"


def test_time_limit(served, tmp_path):
    _, shas, _ = served
    assert fetch(tmp_path, shas[-1], deadline=Deadline(0)) == "time_limit"


@pytest.mark.parametrize("status", [500, 301])
def test_server_errors(served, tmp_path, status):
    _, shas, state = served
    state["status"] = status
    assert fetch(tmp_path, shas[-1]) == "fetch_failed"


def test_unknown_commit(served, tmp_path):
    assert fetch(tmp_path, "0" * 40) == "fetch_failed"


def test_unreachable(tmp_path, monkeypatch):
    monkeypatch.setattr(history_github, "_remote_url", lambda source: "http://127.0.0.1:9/o/r.git")
    assert fetch(tmp_path, "1" * 40) == "fetch_failed"


def test_link_has_history(served, tmp_path, monkeypatch):
    origin, shas, _ = served
    sha = shas[-1]
    fake = FakeGitHub()
    fake.serve("https://api.github.com/repos/o/r/commits/HEAD", body=sha.encode())
    fake.serve(f"https://codeload.github.com/o/r/tar.gz/{sha}", body=tar_of_dir(origin, f"o-r-{sha[:7]}", exclude={".git"}))
    monkeypatch.setattr(github, "_open", fake)

    code, out, err = run_analyze("https://github.com/o/r")
    assert code == 0, err
    history = json.loads(out)["history"]
    assert (history["status"], history["commit"], history["commits_read"]) == ("available", sha, 3)
    assert history["files"] == [
        {"path": "a.py", "commits": 1, "authors": 1},
        {"path": "b.py", "commits": 3, "authors": 2},
        {"path": "c.py", "commits": 1, "authors": 1},
    ]
    assert run_analyze("https://github.com/o/r")[1] == out


def test_link_without_server(tmp_path, monkeypatch):
    origin = tmp_path / "origin"
    sha = make_repo(origin, COMMITS)[-1]
    fake = FakeGitHub()
    fake.serve("https://api.github.com/repos/o/r/commits/HEAD", body=sha.encode())
    fake.serve(f"https://codeload.github.com/o/r/tar.gz/{sha}", body=tar_of_dir(origin, f"o-r-{sha[:7]}", exclude={".git"}))
    monkeypatch.setattr(github, "_open", fake)

    code, out, err = run_analyze("https://github.com/o/r")
    assert code == 0, err
    assert json.loads(out)["history"]["reason"] == "fetch_failed"
    assert "history: not available (fetch_failed)" in err
