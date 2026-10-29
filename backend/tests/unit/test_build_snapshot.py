"""build() with a caller-supplied snapshot id (specs/002-repo-ingest spec.md FR-014, FR-015)."""

import pytest

from conftest import FIXTURES
from graphora.graph.build import build
from graphora.graph.serialize import dumps
from graphora.ingest.walk import Deadline

FIXTURE_NAMES = sorted(p.name for p in FIXTURES.iterdir() if (p / "repo").is_dir())
SHA = "a" * 40


def _build(name, **kwargs):
    doc, _ = build(FIXTURES / name / "repo", 5000, 50 * 1024 * 1024, Deadline(300), **kwargs)
    return doc


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_snapshot_none_is_unchanged(name):
    assert dumps(_build(name, snapshot=None)) == dumps(_build(name))


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_given_snapshot_is_used_everywhere(name):
    default = _build(name)
    doc = _build(name, snapshot=SHA)
    assert doc.snapshot == SHA
    assert all(e.snapshot == SHA for e in doc.edges)
    assert dumps(doc) == dumps(default).replace(default.snapshot.encode(), SHA.encode())
