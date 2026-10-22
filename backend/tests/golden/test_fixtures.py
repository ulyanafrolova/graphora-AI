"""Golden tests: every fixture's output, projected, must equal its hand-checked expected.json."""

import json
import shutil

import pytest

from conftest import FIXTURES, REPO_ROOT, project, run_analyze

FIXTURE_NAMES = sorted(p.name for p in FIXTURES.iterdir() if (p / "expected.json").is_file())


def _normalize(section: str, value):
    if section == "nodes":
        return sorted(value, key=lambda n: n["id"])
    if section == "edges":
        return sorted(value, key=lambda e: (e["source"], e["line"], e["target"], e["symbol"] or ""))
    if section in ("coverage", "skipped"):
        return sorted(value, key=lambda x: x["path"])
    return value


def _analyze(path):
    code, out, err = run_analyze(path)
    assert code == 0, err
    return out


@pytest.mark.parametrize("name", FIXTURE_NAMES)
@pytest.mark.parametrize("section", ["nodes", "edges", "coverage", "skipped", "snapshot_kind"])
def test_matches_expected(name, section, validator):
    expected = json.loads((FIXTURES / name / "expected.json").read_text(encoding="utf-8"))
    if section not in expected:
        pytest.skip(f"{name} has no {section} section")
    doc = json.loads(_analyze(FIXTURES / name / "repo"))
    validator.validate(doc)
    actual = project(doc, {section})[section]
    assert _normalize(section, actual) == _normalize(section, expected[section])


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_provenance_consistent(name):
    doc = json.loads(_analyze(FIXTURES / name / "repo"))
    for edge in doc["edges"]:
        assert edge["snapshot"] == doc["snapshot"]
        assert edge["extractor"] == "python-adapter@0.1.0"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_determinism(name, tmp_path):
    source = FIXTURES / name / "repo"
    first = _analyze(source)
    for _ in range(9):
        assert _analyze(source) == first
    copy = tmp_path / "deep" / "other" / "path"
    shutil.copytree(source, copy, symlinks=True)
    assert _analyze(copy) == first
    text = first.decode("utf-8")
    assert str(REPO_ROOT) not in text and str(tmp_path) not in text
