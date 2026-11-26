"""SC-001 / Principle VIII: a stored and read-back graph is byte-identical to plain CLI output, on every run."""

from __future__ import annotations

import pytest

from conftest import FIXTURES, analyze_fixture, run_analyze

pytestmark = pytest.mark.db

NAMES = sorted(p.name for p in FIXTURES.iterdir() if (p / "repo").is_dir())


def test_every_fixture_round_trips_three_times(store):
    expected = {}
    for name in NAMES:
        code, out, err = run_analyze(FIXTURES / name / "repo")
        assert code == 0, err
        expected[name] = out

    runs = []
    for _ in range(3):
        store._conn.execute("TRUNCATE files, analyses, blobs")
        run = {}
        for name in NAMES:
            analysis = analyze_fixture(name)
            assert store.put(name, analysis).action == "stored"
            run[name] = store.get_analysis(name, analysis.doc.snapshot).graph
            assert run[name] == expected[name], name
        runs.append(run)
    assert runs[0] == runs[1] == runs[2]


def test_list_files_matches_get_file(store):
    for name in ("py-cycles", "ts-app", "csharp-multiproject"):
        analysis = analyze_fixture(name)
        store.put(name, analysis)
        listed = store.list_files(name, analysis.doc.snapshot)
        assert [p for p, _, _ in listed] == sorted(p for p, _, _ in listed) and listed
        for path, has_text, line_count in listed:
            found = store.get_file(name, analysis.doc.snapshot, path)
            assert (found.has_text, found.line_count) == (has_text, line_count)
    assert store.list_files("nope", "content:0000000000000000") == []
