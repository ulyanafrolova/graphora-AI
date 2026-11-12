"""The analysis store (005 contracts/store-api.md; FR-001 … FR-010, FR-012, FR-014; SC-003, SC-006)."""

from __future__ import annotations

import dataclasses
import threading

import psycopg
import pytest

from conftest import FIXTURES, analyze_dir, analyze_fixture
from graphora.graph.build import current_extractors
from graphora.graph.serialize import dumps
from graphora.store import InvalidAnalysis, Store, StoreUnavailable

pytestmark = pytest.mark.db

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


def _dump_tables(store: Store):
    conn = store._conn
    return tuple(
        conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2, 3").fetchall() if table != "blobs"
        else conn.execute("SELECT * FROM blobs ORDER BY 1").fetchall()
        for table in ("analyses", "files", "blobs")
    )


# --- opening ---------------------------------------------------------------------------------------------


def test_opens_with_network_blocked(store):
    assert store._conn.execute("SELECT 1").fetchone() == (1,)


def test_open_is_idempotent(database_url, store):
    second = Store.open(database_url)
    second.close()


def test_wrong_store_version(database_url, store):
    store._conn.execute("UPDATE store_meta SET value = '99' WHERE key = 'store_version'")
    try:
        with pytest.raises(StoreUnavailable, match="store version 99, expected 1"):
            Store.open(database_url)
    finally:
        store._conn.execute("UPDATE store_meta SET value = '1' WHERE key = 'store_version'")


def test_unreachable_database_hides_password():
    with pytest.raises(StoreUnavailable) as info:
        Store.open("postgresql://u:secret-pw@127.0.0.1:1/x")
    assert "secret-pw" not in info.value.reason
    assert "secret-pw" not in str(info.value)


# --- put, reuse, replace ---------------------------------------------------------------------------------


def test_store_then_reuse(store):
    analysis = analyze_fixture("py-flat")
    first = store.put("py-flat", analysis)
    assert first.action == "stored"
    stored = store.get_analysis("py-flat", analysis.doc.snapshot)
    assert stored.graph == dumps(analysis.doc)
    assert stored.schema_version == 6
    assert stored.extractors == current_extractors()
    assert stored.warnings == tuple(sorted(analysis.warnings))
    assert first.analysis == stored

    before = _dump_tables(store)
    second = store.put("py-flat", analysis)
    assert second.action == "reused"
    assert second.analysis == stored
    assert _dump_tables(store) == before


def test_warnings_are_stored(tmp_path, store):
    (tmp_path / "tsconfig.json").write_text("{ not json")
    (tmp_path / "a.ts").write_text("export const a = 1\n")
    analysis = analyze_dir(tmp_path)
    assert analysis.warnings == ("tsconfig.json",)
    store.put("w", analysis)
    assert store.get_analysis("w", analysis.doc.snapshot).warnings == ("tsconfig.json",)


def test_stale_versions_are_replaced(store):
    analysis = analyze_fixture("ts-app")
    store.put("ts-app", analysis)
    store._conn.execute("UPDATE analyses SET extractors = '{\"js-adapter\":\"0.0.1\"}'")
    assert store.find_reusable("ts-app", analysis.doc.snapshot) is None
    result = store.put("ts-app", analysis)
    assert result.action == "replaced"
    assert store._conn.execute("SELECT count(*) FROM analyses").fetchone() == (1,)
    assert store.find_reusable("ts-app", analysis.doc.snapshot) is not None
    paths = [r[0] for r in store._conn.execute("SELECT path FROM files ORDER BY path").fetchall()]
    assert paths == sorted(f.path for f in analysis.doc.files)


def test_files_match_coverage(tmp_path, store):
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("")
    (tmp_path / "logo.png").write_bytes(PNG)
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "x.py").write_text("x = 1\n")
    analysis = analyze_dir(tmp_path)
    store.put("t", analysis)
    rows = {
        r[0]: r[1:]
        for r in store._conn.execute("SELECT path, has_text, line_count, size, sha256 FROM files").fetchall()
    }
    assert sorted(rows) == sorted(f.path for f in analysis.doc.files)
    assert ".venv/x.py" not in rows and ".venv" not in rows
    assert rows["a.py"][:3] == (True, 1, 9)
    assert rows["logo.png"] == (False, 0, len(PNG), None)
    assert store._conn.execute("SELECT count(*) FROM blobs").fetchone() == (2,)  # a.py and the empty b.py


def test_unreadable_file_row(tmp_path, store):
    (tmp_path / "a.py").write_text("x = 1\n")
    analysis = analyze_dir(tmp_path)
    # simulate a file that could not be opened during analysis
    doc = analysis.doc
    files = tuple(dataclasses.replace(f, flags=("unreadable",)) if f.path == "a.py" else f for f in doc.files)
    analysis = dataclasses.replace(analysis, doc=dataclasses.replace(doc, files=files), contents={})
    store.put("u", analysis)
    assert store._conn.execute("SELECT has_text, line_count, size, sha256 FROM files").fetchall() == [(False, 0, None, None)]


def test_blobs_are_shared(tmp_path, store):
    (tmp_path / "a.py").write_text("x = 1\n")
    first = analyze_dir(tmp_path)
    (tmp_path / "b.py").write_text("y = 2\n")
    second = analyze_dir(tmp_path)
    assert first.doc.snapshot != second.doc.snapshot
    store.put("r", first)
    store.put("r", second)
    assert store._conn.execute("SELECT count(*) FROM blobs").fetchone() == (2,)
    assert store._conn.execute("SELECT count(*) FROM files").fetchone() == (3,)


def test_only_readme(tmp_path, store):
    (tmp_path / "README.md").write_text("# hi\n")
    analysis = analyze_dir(tmp_path)
    store.put("readme", analysis)
    doc = store.get_analysis("readme", analysis.doc.snapshot)
    assert b'"nodes": []' in doc.graph and b'"edges": []' in doc.graph
    assert store._conn.execute("SELECT path, has_text FROM files").fetchall() == [("README.md", True)]


def test_failed_write_leaves_nothing(monkeypatch, store):
    analysis = analyze_fixture("py-flat")
    store.put("py-flat", analysis)
    store._conn.execute("UPDATE analyses SET extractors = '{}'")  # stale: the next put replaces
    before = _dump_tables(store)

    real = psycopg.Cursor.executemany

    def failing(self, query, params_seq, *args, **kwargs):
        if "INSERT INTO files" in str(query):
            raise RuntimeError("boom")
        return real(self, query, params_seq, *args, **kwargs)

    monkeypatch.setattr(psycopg.Cursor, "executemany", failing)
    with pytest.raises(RuntimeError, match="boom"):
        store.put("py-flat", analysis)
    with pytest.raises(RuntimeError, match="boom"):
        store.put("other", analysis)
    monkeypatch.undo()
    assert _dump_tables(store) == before
    assert store.get_analysis("other", analysis.doc.snapshot) is None


def test_concurrent_puts(database_url, store):
    analysis = analyze_fixture("mixed-fullstack")
    stores = [Store.open(database_url), Store.open(database_url)]
    results = [None, None]
    barrier = threading.Barrier(2)

    def run(i):
        barrier.wait()
        results[i] = stores[i].put("m", analysis)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for s in stores:
        s.close()
    assert sorted(r.action for r in results) == ["reused", "stored"]
    assert results[0].analysis == results[1].analysis
    assert store._conn.execute("SELECT count(*) FROM analyses").fetchone() == (1,)


def test_invalid_document_is_not_stored(monkeypatch, store):
    import graphora.store.store as module

    analysis = analyze_fixture("py-flat")
    monkeypatch.setattr(module, "dumps", lambda doc: b'{"schema_version": 2}')
    with pytest.raises(InvalidAnalysis, match="does not match the schema"):
        store.put("py-flat", analysis)
    assert store._conn.execute("SELECT count(*) FROM analyses").fetchone() == (0,)


def test_contents_must_match_coverage(store):
    analysis = analyze_fixture("py-flat")
    extra = dataclasses.replace(analysis, contents={**analysis.contents, "nope.py": b""})
    with pytest.raises(InvalidAnalysis, match="nope.py"):
        store.put("py-flat", extra)
    some = next(iter(analysis.contents))
    missing = dataclasses.replace(analysis, contents={k: v for k, v in analysis.contents.items() if k != some})
    with pytest.raises(InvalidAnalysis, match="missing"):
        store.put("py-flat", missing)
    assert store._conn.execute("SELECT count(*) FROM analyses").fetchone() == (0,)


def test_repository_name_limit(store):
    analysis = analyze_fixture("py-flat")
    with pytest.raises(InvalidAnalysis, match="longer than 300 characters"):
        store.put("x" * 301, analysis)
    store.put("x" * 300, analysis)


def test_survives_reopen(database_url, store):
    names = sorted(p.name for p in FIXTURES.iterdir() if (p / "repo").is_dir())
    for name in names:
        store.put(name, analyze_fixture(name))
    before = _dump_tables(store)
    store.close()
    reopened = Store.open(database_url)
    try:
        assert _dump_tables(reopened) == before
    finally:
        reopened.close()


def test_reconnects_after_lost_connection(store):
    store._conn.close()
    assert store.list_repositories() == ()


# --- reads -----------------------------------------------------------------------------------------------


def test_list_repositories(tmp_path, store):
    store.put("ts-app", analyze_fixture("ts-app"))
    store.put("py-flat", analyze_fixture("py-flat"))
    (tmp_path / "a.py").write_text("")
    second = analyze_dir(tmp_path)
    store.put("py-flat", second)
    listed = store.list_repositories()
    assert [name for name, _ in listed] == ["py-flat", "ts-app"]
    snapshots = dict(listed)["py-flat"]
    assert list(snapshots) == sorted(snapshots) and len(snapshots) == 2


def test_get_file(tmp_path, store):
    (tmp_path / "a.py").write_text("l1\nl2\nl3\nl4\nl5\n")
    (tmp_path / "logo.png").write_bytes(PNG)
    (tmp_path / "empty.ts").write_text("")
    analysis = analyze_dir(tmp_path)
    snap = analysis.doc.snapshot
    store.put("f", analysis)

    whole = store.get_file("f", snap, "a.py")
    assert (whole.has_text, whole.line_count, whole.start, whole.end) == (True, 5, 1, 5)
    assert whole.lines == ("l1", "l2", "l3", "l4", "l5")
    part = store.get_file("f", snap, "a.py", 3, 5)
    assert (part.start, part.end, part.lines) == (3, 5, ("l3", "l4", "l5"))
    clamped = store.get_file("f", snap, "a.py", 4, 99)
    assert (clamped.end, clamped.lines) == (5, ("l4", "l5"))
    assert store.get_file("f", snap, "a.py", None, 2).lines == ("l1", "l2")
    for start, end in ((0, 2), (3, 2), (6, None), (-1, None)):
        with pytest.raises(ValueError):
            store.get_file("f", snap, "a.py", start, end)

    png = store.get_file("f", snap, "logo.png")
    assert (png.has_text, png.line_count, png.start, png.end, png.lines) == (False, 0, 0, 0, ())
    with pytest.raises(ValueError, match="no text"):
        store.get_file("f", snap, "logo.png", 1, 1)
    empty = store.get_file("f", snap, "empty.ts")
    assert (empty.has_text, empty.line_count, empty.lines) == (True, 0, ())

    assert store.get_file("f", snap, "missing.py") is None
    assert store.get_file("f", "content:0000000000000000", "a.py") is None
    assert store.get_file("nope", snap, "a.py") is None
    assert store.has_repository("f") and not store.has_repository("nope")
    assert store.has_snapshot("f", snap) and not store.has_snapshot("f", "content:0000000000000000")
