"""Hotspots: commits × transitive dependents (specs/014-hotspots research § R8, contracts/interfaces.md)."""

import dataclasses

import pytest

from graphora.graph.model import FileHistory, History, not_available
from graphora.graph.queries import hotspots, index
from graphora.graph.results import render_text
from synthetic import edge, make_doc

SHA = "f" * 40


def history(files, **changes):
    values = dict(
        status="available", reason=None, commit=SHA, window_start="2025-01-01T00:00:00Z",
        newest="2026-01-01T00:00:00Z", oldest="2025-02-01T00:00:00Z", commits_read=40, merges_skipped=3,
        shallow_skipped=0, local_changes=False,
        files=tuple(FileHistory(p, c, a) for p, (c, a) in sorted(files.items())),
    )
    values.update(changes)
    return History(**values)


EDGES = [
    edge("b.py", "a.py"),
    edge("c.py", "b.py"),
    edge("d.py", "a.py", type_only=True),
    edge("h.py", "g.py"),
    edge("c.py", "e.py"),
]
FILES = {"a.py": (5, 1), "b.py": (8, 3), "c.py": (20, 2), "g.py": (15, 4)}


def ix(files=FILES, **changes):
    return index(dataclasses.replace(make_doc(EDGES), history=history(files, **changes)))


def rows(answer):
    return [(i.node, i.score, i.commits, i.authors, i.transitive_dependents, i.direct_dependents) for i in answer.items]


def test_score_and_order():
    assert rows(hotspots(ix())) == [
        ("file:g.py", 15, 15, 4, 1, 1),
        ("file:a.py", 15, 5, 1, 3, 2),
        ("file:b.py", 8, 8, 3, 1, 1),
    ]


def test_left_out_without_dependents_or_history():
    nodes = [i.node for i in hotspots(ix()).items]
    assert "file:c.py" not in nodes  # 20 commits, no dependents
    assert "file:e.py" not in nodes  # a dependent, no commits


def test_path_breaks_ties():
    answer = hotspots(ix({"b.py": (2, 1), "g.py": (2, 1)}))
    assert [i.node for i in answer.items] == ["file:b.py", "file:g.py"]


def test_without_type_only_links():
    answer = hotspots(ix(), include_type_only=False)
    assert ("file:a.py", 10, 5, 1, 2, 1) in rows(answer)
    assert answer.options == {"include_type_only": False, "limit": 10}


def test_limit():
    answer = hotspots(ix(), limit=1)
    assert len(answer.items) == 1
    assert (answer.total, answer.truncated) == (3, True)
    with pytest.raises(ValueError):
        hotspots(ix(), limit=-1)


def test_history_without_files_in_answer():
    out = hotspots(ix()).to_dict()
    assert out["question"] == "hotspots" and out["target"] is None
    assert out["history"]["commits_read"] == 40 and "files" not in out["history"]
    assert out["items"][0]["score"] == 15 and out["items"][0]["authors"] == 4


def test_not_available():
    doc = dataclasses.replace(make_doc(EDGES), history=not_available("zip"))
    answer = hotspots(index(doc))
    assert answer.items == () and answer.total == 0
    assert answer.to_dict()["history"]["reason"] == "zip"
    assert "history: not available (zip)" in render_text(answer)


def test_text():
    text = render_text(hotspots(ix(), limit=2))
    assert text.splitlines()[1:5] == [
        "g.py  score 15  commits 15  authors 4  transitive 1  direct 1",
        "a.py  score 15  commits 5  authors 1  transitive 3  direct 2",
        "history: 40 commits from 2025-02-01 to 2026-01-01 (window from 2025-01-01), 3 merges not counted",
        "total: 3",
    ]


@pytest.mark.parametrize(
    ("changes", "line"),
    [
        ({"status": "partial"}, "history: partial (time limit), 40 commits read back to 2025-02-01"),
        ({"local_changes": True, "merges_skipped": 0},
         "history: 40 commits from 2025-02-01 to 2026-01-01 (window from 2025-01-01); uncommitted changes not counted"),
        ({"shallow_skipped": 2, "merges_skipped": 0},
         "history: 40 commits from 2025-02-01 to 2026-01-01 (window from 2025-01-01); 2 commits not counted (shallow history)"),
    ],
)
def test_history_line(changes, line):
    assert line in render_text(hotspots(ix(**changes))).splitlines()


def test_skipped_line():
    doc = dataclasses.replace(make_doc(EDGES), history=not_available("skipped"))
    assert "history: not available (skipped by request)" in render_text(hotspots(index(doc)))
