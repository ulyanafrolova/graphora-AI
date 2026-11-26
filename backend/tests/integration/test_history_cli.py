"""`graphora analyze` writes history, `graphora query … hotspots` ranks it (specs/014-hotspots, US1, US2)."""

import json

import pytest

from archives import zip_of_dir
from conftest import run_analyze, run_query
from history_repos import make_repo, make_shallow

ZELDA = "Zelda Quorn <zelda@quorn.test>"
OTTO = "Otto Vexley <otto@vexley.test>"

COMMITS = [
    {
        "files": {
            "auth/__init__.py": b"",
            "auth/service.py": b"def login():\n    return 1\n",
            "api/__init__.py": b"",
            "api/routes.py": b"from auth.service import login\n",
            "cli.py": b"from api.routes import login\n",
            "main.py": b"from auth.service import login\n",
        },
        "author": ZELDA,
    },
    {"files": {"auth/service.py": b"def login():\n    return 2\n"}, "author": ZELDA},
    {"files": {"auth/service.py": b"def login():\n    return 3\n", "api/routes.py": b"from auth.service import login\nx = 1\n"}, "author": OTTO},
    {"files": {"auth/service.py": b"def login():\n    return 4\n"}, "author": "O. Vexley <OTTO@Vexley.test>"},
]


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "app"
    shas = make_repo(path, COMMITS)
    return path, shas


def analyze(path, *args):
    code, out, err = run_analyze(path, *args)
    assert code == 0, err
    return out, err


def test_history_written(repo):
    path, shas = repo
    out, err = analyze(path)
    history = json.loads(out)["history"]
    assert history["status"] == "available" and history["commit"] == shas[-1]
    assert history["commits_read"] == 4
    assert history["files"] == [
        {"path": "api/__init__.py", "commits": 1, "authors": 1},
        {"path": "api/routes.py", "commits": 2, "authors": 2},
        {"path": "auth/__init__.py", "commits": 1, "authors": 1},
        {"path": "auth/service.py", "commits": 4, "authors": 2},
        {"path": "cli.py", "commits": 1, "authors": 1},
        {"path": "main.py", "commits": 1, "authors": 1},
    ]
    assert "graphora: info: history: 4 commits from " in err


def test_repeat_gives_same_bytes(repo):
    path, _ = repo
    assert analyze(path)[0] == analyze(path)[0]


def test_no_names_or_emails(repo, tmp_path):
    path, _ = repo
    out, _ = analyze(path)
    graph = tmp_path / "graph.json"
    graph.write_bytes(out)
    code, answer, _ = run_query(str(graph), "hotspots", "--format", "json")
    assert code == 0
    for text in (out, answer):
        for word in (b"Zelda", b"Quorn", b"Otto", b"Vexley", b"zelda@", b"otto@"):
            assert word.lower() not in text.lower()


def test_query_hotspots(repo, tmp_path):
    path, _ = repo
    graph = tmp_path / "graph.json"
    graph.write_bytes(analyze(path)[0])
    code, out, _ = run_query(str(graph), "hotspots")
    assert code == 0
    lines = out.decode().splitlines()
    assert lines[1:3] == [
        "auth/service.py  score 12  commits 4  authors 2  transitive 3  direct 2",
        "api/routes.py  score 2  commits 2  authors 2  transitive 1  direct 1",
    ]
    assert "total: 2" in lines
    code, out, _ = run_query(str(graph), "hotspots", "--format", "json", "--limit", "1")
    answer = json.loads(out)
    assert [i["node"] for i in answer["items"]] == ["file:auth/service.py"]
    assert (answer["total"], answer["truncated"], answer["options"]["limit"]) == (2, True, 1)


@pytest.mark.parametrize(
    "args",
    [
        ("hotspots", "auth/service.py"),
        ("hotspots", "--symbol", "login"),
        ("hotspots", "--max-depth", "2"),
        ("hotspots", "--follow-barrels"),
        ("hotspots", "--level", "project"),
    ],
)
def test_usage_errors(repo, tmp_path, args):
    path, _ = repo
    graph = tmp_path / "graph.json"
    graph.write_bytes(analyze(path)[0])
    code, _, _ = run_query(str(graph), *args)
    assert code == 2


def history_of(path, *args):
    out, err = analyze(path, *args)
    return json.loads(out)["history"], err


def test_zip(repo, tmp_path):
    path, _ = repo
    archive = tmp_path / "app.zip"
    archive.write_bytes(zip_of_dir(path))
    history, err = history_of(archive)
    assert (history["status"], history["reason"], history["files"]) == ("not_available", "zip", [])
    assert "graphora: info: history: not available (zip)" in err


def test_plain_folder(tmp_path):
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("")
    history, err = history_of(tmp_path)
    assert (history["status"], history["reason"]) == ("not_available", "no_git")
    assert "history: not available (no_git)" in err


def test_no_history(repo):
    path, _ = repo
    history, err = history_of(path, "--no-history")
    assert (history["status"], history["reason"]) == ("not_available", "skipped")
    assert "graphora: info: history: not available (skipped by request)" in err


def test_alternates(repo):
    path, _ = repo
    (path / ".git" / "objects" / "info").mkdir(exist_ok=True)
    (path / ".git" / "objects" / "info" / "alternates").write_text("/elsewhere/objects\n")
    assert history_of(path)[0]["reason"] == "no_git"


def test_missing_old_commit(repo):
    path, shas = repo
    (path / ".git" / "objects" / shas[0][:2] / shas[0][2:]).unlink()
    out, _ = analyze(path)
    doc = json.loads(out)
    assert doc["snapshot"] == shas[-1]
    assert (doc["history"]["status"], doc["history"]["reason"]) == ("not_available", "unreadable")


def test_dirty(repo):
    path, shas = repo
    (path / "main.py").write_text("from auth.service import login\nlogin()\n")
    out, err = analyze(path)
    doc = json.loads(out)
    assert "+dirty:" in doc["snapshot"]
    assert doc["history"]["commit"] == shas[-1] and doc["history"]["local_changes"] is True
    assert {"path": "main.py", "commits": 1, "authors": 1} in doc["history"]["files"]
    assert "; uncommitted changes not counted" in err


def test_shallow(repo):
    path, shas = repo
    make_shallow(path, [shas[1]])
    history, err = history_of(path)
    assert (history["status"], history["commits_read"], history["shallow_skipped"]) == ("available", 2, 1)
    assert history["files"] == [
        {"path": "api/routes.py", "commits": 1, "authors": 1},
        {"path": "auth/service.py", "commits": 2, "authors": 1},
    ]
    assert "; 1 commits not counted (shallow history)" in err
