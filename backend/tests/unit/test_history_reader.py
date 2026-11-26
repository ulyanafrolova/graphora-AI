"""Counting commits and authors per file (specs/014-hotspots research § R3, R4). Expected counts are by hand."""

from dulwich.repo import Repo

from graphora.history.reader import read_history
from graphora.ingest.walk import Deadline
from history_repos import DAY, T0, make_repo

YEAR = 365 * DAY


def read(path, sha, paths, shallow=frozenset(), deadline=None):
    repo = Repo(str(path))
    try:
        return read_history(repo.object_store, sha, frozenset(paths), shallow, deadline or Deadline(600))
    finally:
        repo.close()


def counts(history):
    return {f.path: (f.commits, f.authors) for f in history.files}


def test_commits_and_authors(tmp_path):
    shas = make_repo(
        tmp_path,
        [
            {"files": {"auth/service.py": b"1", "api.py": b"1"}},
            {"files": {"auth/service.py": b"2"}},
            {"files": {"auth/service.py": b"3"}, "author": "Bob <BOB@Example.com>"},
            {"files": {"auth/service.py": b"4"}, "author": "Robert <bob@example.com>"},
            {"files": {"auth/service.py": b"5", "api.py": b"2"}, "author": "Eve <eve@example.com>"},
        ],
    )
    history = read(tmp_path, shas[-1], {"auth/service.py", "api.py"})
    assert history.status == "available"
    assert history.commit == shas[-1]
    assert counts(history) == {"api.py": (2, 2), "auth/service.py": (5, 3)}
    assert history.commits_read == 5
    assert (history.merges_skipped, history.shallow_skipped, history.local_changes) == (0, 0, False)


def test_merge_not_counted_branches_are(tmp_path):
    shas = make_repo(
        tmp_path,
        [
            {"files": {"a.py": b"0", "b.py": b"0"}},
            {"files": {"a.py": b"1"}},
            {"files": {"b.py": b"1"}, "parents": [0]},
            {"files": {"b.py": b"1"}, "parents": [1, 2]},
        ],
    )
    history = read(tmp_path, shas[-1], {"a.py", "b.py"})
    assert counts(history) == {"a.py": (2, 1), "b.py": (2, 1)}
    assert history.commits_read == 3
    assert history.merges_skipped == 1


def test_delete_and_rename(tmp_path):
    shas = make_repo(
        tmp_path,
        [
            {"files": {"old.py": b"x", "gone.py": b"y", "keep.py": b"z"}},
            {"files": {"old.py": None, "new.py": b"x"}},
            {"files": {"gone.py": None}},
        ],
    )
    history = read(tmp_path, shas[-1], {"new.py", "keep.py", "old.py", "gone.py"})
    assert counts(history) == {"gone.py": (1, 1), "keep.py": (1, 1), "new.py": (1, 1), "old.py": (1, 1)}
    assert history.commits_read == 3


def test_root_commit_counts_its_files(tmp_path):
    shas = make_repo(tmp_path, [{"files": {"a.py": b"1", "pkg/b.py": b"2"}}])
    history = read(tmp_path, shas[0], {"a.py", "pkg/b.py"})
    assert counts(history) == {"a.py": (1, 1), "pkg/b.py": (1, 1)}


def test_window(tmp_path):
    head = T0 + 2 * YEAR
    shas = make_repo(
        tmp_path,
        [
            {"files": {"a.py": b"0"}, "time": head - YEAR - 2 * DAY},
            {"files": {"a.py": b"1"}, "time": head - YEAR - 1},
            {"files": {"a.py": b"2"}, "time": head - YEAR},
            {"files": {"a.py": b"3"}, "time": head},
        ],
    )
    history = read(tmp_path, shas[-1], {"a.py"})
    assert counts(history) == {"a.py": (2, 1)}
    assert history.window_start == "2026-06-15T15:06:40Z"
    assert history.newest == "2027-06-15T15:06:40Z"
    assert history.oldest == "2026-06-15T15:06:40Z"


def test_walk_stops_at_window(tmp_path):
    head = T0 + 2 * YEAR
    shas = make_repo(
        tmp_path,
        [
            {"files": {"a.py": b"0"}, "time": head - 10 * DAY},
            {"files": {"a.py": b"1"}, "time": head - 2 * YEAR},
            {"files": {"a.py": b"2"}, "time": head},
        ],
    )
    assert counts(read(tmp_path, shas[-1], {"a.py"})) == {"a.py": (1, 1)}


def test_only_given_paths(tmp_path):
    shas = make_repo(tmp_path, [{"files": {"a.py": b"1", "README.md": b"r", ".venv/x.py": b"v"}}])
    assert counts(read(tmp_path, shas[0], {"a.py"})) == {"a.py": (1, 1)}


def test_no_commits_touch_paths(tmp_path):
    shas = make_repo(tmp_path, [{"files": {"README.md": b"r"}}])
    history = read(tmp_path, shas[0], {"a.py"})
    assert history.status == "available"
    assert history.files == ()
    assert history.commits_read == 1


def test_repeatable(tmp_path):
    shas = make_repo(tmp_path, [{"files": {"a.py": b"0"}}, {"files": {"a.py": b"1", "b.py": b"1"}}])
    assert read(tmp_path, shas[-1], {"a.py", "b.py"}) == read(tmp_path, shas[-1], {"a.py", "b.py"})
