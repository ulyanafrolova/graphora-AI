"""`graphora analyze --store` and `graphora serve` (005 contracts/cli.md; FR-008, FR-011, FR-020, SC-002, SC-006)."""

from __future__ import annotations

import tempfile

import psycopg
import pytest

from archives import make_tar_gz, make_zip
from conftest import FIXTURES, run_analyze
from fake_github import FakeGitHub
from graphora import cli
from graphora.ingest import github
from graphora.store import Store, StoreUnavailable

FLAT = FIXTURES / "py-flat" / "repo"
SHA = "0123456789abcdef0123456789abcdef01234567"
LINK = "https://github.com/o/r"
API = "https://api.github.com/repos/o/r/commits/HEAD"
TARBALL = f"https://codeload.github.com/o/r/tar.gz/{SHA}"
TAR = make_tar_gz(
    [
        ("o-r-0123456", "dir"),
        ("o-r-0123456/a.ts", "file", "import { b } from './b'\n"),
        ("o-r-0123456/b.ts", "file", "export const b = 1\n"),
        ("o-r-0123456/tsconfig.json", "file", "{ broken"),
    ],
    SHA,
)


@pytest.fixture
def fake(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(github, "_open", fake)
    fake.serve(API, body=SHA.encode())
    fake.serve(TARBALL, body=TAR)
    return fake


@pytest.fixture
def db(store, database_url, monkeypatch):
    monkeypatch.setenv("GRAPHORA_DATABASE_URL", database_url)
    return store


def _lines(err: str, prefix: str) -> list[str]:
    return [line for line in err.splitlines() if line.startswith(prefix)]


# --- analyze --store -------------------------------------------------------------------------------------


@pytest.mark.db
def test_store_local_folder(db):
    plain = run_analyze(FLAT)
    first = run_analyze(FLAT, "--store")
    second = run_analyze(FLAT, "--store")
    assert plain[0] == first[0] == second[0] == 0
    assert first[1] == plain[1] == second[1]
    snapshot = db.list_repositories()[0][1][0]
    assert f"graphora: info: stored repo {snapshot}" in first[2]
    assert f"graphora: info: reused repo {snapshot}" in second[2]
    assert _lines(first[2], "graphora: info: analyzed") == _lines(plain[2], "graphora: info: analyzed")


@pytest.mark.db
def test_store_with_out(db, tmp_path):
    out = tmp_path / "g.json"
    code, stdout, err = run_analyze(FLAT, "--store", "--out", str(out))
    assert code == 0, err and stdout == b""
    assert out.read_bytes() == run_analyze(FLAT)[1]


@pytest.mark.db
def test_database_option(store, database_url, monkeypatch):
    monkeypatch.delenv("GRAPHORA_DATABASE_URL", raising=False)
    code, _, err = run_analyze(FLAT, "--store", "--database", database_url)
    assert code == 0, err
    assert len(store.list_repositories()) == 1


@pytest.mark.db
def test_github_reuse_skips_download(db, fake):
    first = run_analyze(LINK, "--store")
    assert first[0] == 0, first[2]
    assert fake.urls("api.github.com") == [API]
    assert fake.urls("codeload.github.com") == [TARBALL]
    assert f"graphora: info: fetched github.com/o/r at {SHA}" in first[2]
    assert f"graphora: info: stored github.com/o/r {SHA}" in first[2]

    fake.requests.clear()
    second = run_analyze(LINK, "--store")
    assert second[0] == 0, second[2]
    assert fake.urls("api.github.com") == [API]
    assert fake.urls("codeload.github.com") == []
    assert second[1] == first[1]
    assert "fetched" not in second[2]
    assert f"graphora: info: reused github.com/o/r {SHA}" in second[2]
    warnings = _lines(first[2], "graphora: warning:")
    assert warnings == ["graphora: warning: ignoring tsconfig.json: not valid JSON-with-comments"]
    assert _lines(second[2], "graphora: warning:") == warnings
    assert _lines(second[2], "graphora: info: analyzed") == _lines(first[2], "graphora: info: analyzed")
    order = [line.split(":", 2)[2].split()[0] for line in second[2].splitlines()]
    assert order == ["reused", "ignoring", "analyzed"]


@pytest.mark.db
def test_same_zip_twice(db, tmp_path):
    path = tmp_path / "p.zip"
    path.write_bytes(make_zip([("a.py", "file", "import os\n")]))
    first = run_analyze(path, "--store")
    second = run_analyze(path, "--store")
    assert first[0] == second[0] == 0
    assert first[1] == second[1]
    assert "graphora: info: stored p content:" in first[2]
    assert "graphora: info: reused p content:" in second[2]
    assert db._conn.execute("SELECT count(*) FROM analyses").fetchone() == (1,)


def test_no_database_url(monkeypatch):
    monkeypatch.delenv("GRAPHORA_DATABASE_URL", raising=False)
    code, out, err = run_analyze(FLAT, "--store")
    assert code == 6 and out == b""
    assert "graphora: error: store unavailable: no database URL" in err


def test_unreachable_database(monkeypatch):
    monkeypatch.setenv("GRAPHORA_DATABASE_URL", "postgresql://u:pw-secret@127.0.0.1:1/x")
    code, out, err = run_analyze(FLAT, "--store")
    assert code == 6 and out == b""
    assert "graphora: error: store unavailable:" in err
    assert "pw-secret" not in err


def test_database_without_store():
    code, out, err = run_analyze(FLAT, "--database", "postgresql://x")
    assert code == 2 and out == b""
    assert "graphora: error: --database requires --store" in err


def test_plain_run_never_connects(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("connected without --store")

    monkeypatch.setattr(psycopg, "connect", refuse)
    code, _, err = run_analyze(FLAT)
    assert code == 0, err


@pytest.mark.db
def test_store_failure_writes_nothing(db, monkeypatch, tmp_path):
    def broken(self, repository, analysis):
        raise StoreUnavailable("boom")

    monkeypatch.setattr(Store, "put", broken)
    out = tmp_path / "g.json"
    code, stdout, err = run_analyze(FLAT, "--store", "--out", str(out))
    assert code == 6 and stdout == b""
    assert "graphora: error: store unavailable: boom" in err
    assert not out.exists()
    code, stdout, _ = run_analyze(FLAT, "--store")
    assert code == 6 and stdout == b""


@pytest.mark.db
def test_interrupt_during_store_write(db, monkeypatch, tmp_path):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp))
    monkeypatch.setattr(tempfile, "tempdir", None)
    real = psycopg.Cursor.executemany

    def interrupted(self, query, params_seq, *args, **kwargs):
        if "INSERT INTO files" in str(query):
            raise KeyboardInterrupt
        return real(self, query, params_seq, *args, **kwargs)

    monkeypatch.setattr(psycopg.Cursor, "executemany", interrupted)
    path = tmp_path / "p.zip"
    path.write_bytes(make_zip([("a.py", "file", "import os\n")]))
    code, out, err = run_analyze(path, "--store")
    monkeypatch.undo()
    assert code == 130 and out == b""
    assert "graphora: error: interrupted" in err
    assert db._conn.execute("SELECT count(*) FROM analyses").fetchone() == (0,)
    assert sorted(p.name for p in tmp.iterdir() if p.name.startswith("graphora-")) == []


@pytest.mark.db
def test_invalid_analysis_is_a_usage_error(db, monkeypatch):
    """No CLI source can produce a 301-character name (file names stop at 255 bytes), so the limit itself is
    tested in test_store.py; here only the CLI's handling of `InvalidAnalysis`."""
    from graphora.store import InvalidAnalysis

    def invalid(self, repository, analysis):
        raise InvalidAnalysis("repository name longer than 300 characters")

    monkeypatch.setattr(Store, "put", invalid)
    code, out, err = run_analyze(FLAT, "--store")
    assert code == 2 and out == b""
    assert "graphora: error: cannot store the analysis: repository name longer than 300 characters" in err


# --- serve -----------------------------------------------------------------------------------------------


def test_serve_without_database(monkeypatch):
    import uvicorn

    monkeypatch.delenv("GRAPHORA_DATABASE_URL", raising=False)
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: pytest.fail("listened without a store"))
    assert cli.main(["serve"]) == 6


@pytest.mark.db
def test_serve_binds_localhost_by_default(db, monkeypatch):
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    assert cli.main(["serve"]) == 0
    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "9001"]) == 0
    assert calls == [{"host": "127.0.0.1", "port": 8000}, {"host": "0.0.0.0", "port": 9001}]
