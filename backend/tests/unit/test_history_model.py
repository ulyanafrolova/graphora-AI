"""History rules (specs/014-hotspots data-model.md § History)."""

import pytest

from graphora.graph.model import NOT_COLLECTED, FileHistory, GraphDocument, History

SHA = "a" * 40
DATE = "2026-01-01T00:00:00Z"


def available(**changes):
    values = dict(
        status="available",
        reason=None,
        commit=SHA,
        window_start="2025-01-01T00:00:00Z",
        newest=DATE,
        oldest=DATE,
        commits_read=2,
        merges_skipped=0,
        shallow_skipped=0,
        local_changes=False,
        files=(FileHistory("a.py", 2, 1),),
    )
    values.update(changes)
    return History(**values)


def missing(reason="zip", **changes):
    values = dict(
        status="not_available",
        reason=reason,
        commit=None,
        window_start=None,
        newest=None,
        oldest=None,
        commits_read=0,
        merges_skipped=0,
        shallow_skipped=0,
        local_changes=False,
        files=(),
    )
    values.update(changes)
    return History(**values)


def test_valid():
    assert available().status == "available"
    assert available(status="partial").status == "partial"
    assert missing().reason == "zip"
    assert available(commits_read=0, newest=None, oldest=None, files=()).commits_read == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": None},
        {"commit": SHA},
        {"window_start": DATE},
        {"newest": DATE},
        {"oldest": DATE},
        {"commits_read": 1},
        {"merges_skipped": 1},
        {"shallow_skipped": 1},
        {"local_changes": True},
        {"files": (FileHistory("a.py", 1, 1),)},
        {"reason": "elsewhere"},
    ],
)
def test_not_available_rules(changes):
    with pytest.raises(ValueError):
        missing(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": "zip"},
        {"commit": None},
        {"commit": "abc"},
        {"window_start": None},
        {"newest": None},
        {"oldest": None},
        {"commits_read": 0},
        {"commits_read": -1},
        {"merges_skipped": -1},
        {"status": "partial", "commits_read": 0, "newest": None, "oldest": None, "files": ()},
        {"status": "done"},
        {"files": (FileHistory("b.py", 1, 1), FileHistory("a.py", 1, 1))},
        {"files": (FileHistory("a.py", 1, 1), FileHistory("a.py", 1, 1))},
        {"files": (FileHistory("a.py", 0, 0),)},
        {"files": (FileHistory("a.py", 1, 0),)},
        {"files": (FileHistory("a.py", 1, 2),)},
    ],
)
def test_available_rules(changes):
    with pytest.raises(ValueError):
        available(**changes)


def test_zero_commits_has_no_dates():
    with pytest.raises(ValueError):
        available(commits_read=0, files=())


def test_final():
    assert available().final
    assert not available(status="partial").final
    for reason in ("no_git", "zip", "unreadable"):
        assert missing(reason).final
    for reason in ("skipped", "fetch_failed", "too_large", "time_limit", "not_collected"):
        assert not missing(reason).final


def test_document_default():
    doc = GraphDocument("content:0123456789abcdef", {}, (), (), (), ())
    assert doc.history is NOT_COLLECTED
    assert NOT_COLLECTED.reason == "not_collected"
