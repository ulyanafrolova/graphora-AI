"""The store keeps the best history of a snapshot (specs/014-hotspots FR-018, research § R6)."""

import dataclasses
import json

import pytest

from archives import tar_of_dir
from conftest import analyze_dir, run_analyze
from git_server import allow_loopback, serve_repo
from graphora.graph.model import not_available
from graphora.graph.serialize import dumps
from graphora.history import github as history_github
from graphora.history import history_final
from history_repos import make_repo

pytestmark = pytest.mark.db

COMMITS = [{"files": {"a.py": b"import b\n", "b.py": b"x = 1\n"}}, {"files": {"b.py": b"x = 2\n"}}]


def with_history(analysis, history):
    return dataclasses.replace(analysis, doc=dataclasses.replace(analysis.doc, history=history))


@pytest.fixture
def analysis(tmp_path):
    make_repo(tmp_path / "app", COMMITS)
    result = analyze_dir(tmp_path / "app")
    assert result.doc.history.status == "available"
    return result


def stored_history(store, analysis):
    return json.loads(store.get_analysis("app", analysis.doc.snapshot).graph)["history"]


def test_retryable_replaced_by_final(store, analysis):
    assert store.put("app", with_history(analysis, not_available("skipped"))).action == "stored"
    assert store.put("app", analysis).action == "replaced"
    assert stored_history(store, analysis)["status"] == "available"


def test_final_kept(store, analysis):
    assert store.put("app", analysis).action == "stored"
    assert store.put("app", with_history(analysis, not_available("fetch_failed"))).action == "reused"
    assert stored_history(store, analysis)["status"] == "available"


def test_retryable_kept_for_retryable(store, analysis):
    store.put("app", with_history(analysis, not_available("skipped")))
    assert store.put("app", with_history(analysis, not_available("fetch_failed"))).action == "reused"
    assert stored_history(store, analysis)["reason"] == "skipped"


def test_history_final(analysis):
    assert history_final(dumps(analysis.doc))
    partial = dataclasses.replace(analysis.doc.history, status="partial")
    assert not history_final(dumps(dataclasses.replace(analysis.doc, history=partial)))
    for reason, final in (("zip", True), ("no_git", True), ("unreadable", True), ("skipped", False), ("time_limit", False)):
        doc = dataclasses.replace(analysis.doc, history=not_available(reason))
        assert history_final(dumps(doc)) is final


@pytest.fixture
def db(store, database_url, monkeypatch):
    monkeypatch.setenv("GRAPHORA_DATABASE_URL", database_url)
    return store


def test_github_without_history_is_fetched_again(db, fake_gh, tmp_path, monkeypatch):
    origin = tmp_path / "origin"
    sha = make_repo(origin, COMMITS)[-1]
    fake_gh.serve("https://api.github.com/repos/o/r/commits/HEAD", body=sha.encode())
    tarball = f"https://codeload.github.com/o/r/tar.gz/{sha}"
    fake_gh.serve(tarball, body=tar_of_dir(origin, f"o-r-{sha[:7]}", exclude={".git"}))
    allow_loopback(monkeypatch)
    with serve_repo(origin) as (url, _):
        monkeypatch.setattr(history_github, "_remote_url", lambda source: url)
        first = run_analyze("https://github.com/o/r", "--store", "--no-history")
        assert first[0] == 0 and json.loads(first[1])["history"]["reason"] == "skipped"
        assert "stored github.com/o/r" in first[2]

        second = run_analyze("https://github.com/o/r", "--store")
        assert second[0] == 0, second[2]
        assert json.loads(second[1])["history"]["status"] == "available"
        assert "replaced github.com/o/r" in second[2]

        fake_gh.requests.clear()
        third = run_analyze("https://github.com/o/r", "--store")
        assert "reused github.com/o/r" in third[2]
        assert fake_gh.urls("codeload.github.com") == []
        assert third[1] == second[1]
