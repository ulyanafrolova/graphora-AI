"""GitHub history: commits and trees fetched over git's smart HTTP into a temp repository (specs/014-hotspots
research § R5). A dulwich server on 127.0.0.1 stands in for github.com; it ignores `deepen-since`."""

import json

import pytest
from dulwich.repo import Repo

from archives import tar_of_dir
from conftest import run_analyze
from fake_github import FakeGitHub
from git_server import allow_loopback, serve_repo
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


@pytest.fixture
def served(tmp_path, monkeypatch):
    """A served built repository; `state["status"] = 500 | 301` makes the server fail."""
    origin = tmp_path / "origin"
    shas = make_repo(origin, COMMITS)
    allow_loopback(monkeypatch)
    with serve_repo(origin) as (url, state):
        monkeypatch.setattr(history_github, "_remote_url", lambda source: url)
        yield origin, shas, state


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
    allow_loopback(monkeypatch)
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
    """The suite denies the network, so the fetch from github.com fails like a network error."""
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
