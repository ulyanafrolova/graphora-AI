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
