import copy

import pytest

from graphora.graph.model import CoverageFile, Edge, FileNode, GraphDocument
from graphora.graph.serialize import to_dict

SNAP = "content:0123456789abcdef"


@pytest.fixture
def doc():
    edge = Edge("file:a.py", "file:b.py", "f", 3, 1, SNAP, "resolved", None, "python-adapter@0.1.0", "sha256:0123456789abcdef")
    return to_dict(
        GraphDocument(
            snapshot=SNAP,
            extractors={"python-adapter": "0.1.0"},
            nodes=(FileNode("a.py"), FileNode("b.py")),
            edges=(edge,),
            files=(CoverageFile("a.py", "python", "analyzed"), CoverageFile("b.py", "python", "analyzed")),
            skipped=(),
        )
    )


def test_minimal_document_valid(doc, validator):
    validator.validate(doc)


def _invalid(validator, doc):
    return not validator.is_valid(doc)


def test_edge_without_snippet_hash_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    del bad["edges"][0]["snippet_hash"]
    assert _invalid(validator, bad)


def test_unresolved_without_reason_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["edges"][0].update(confidence="unresolved", target="unresolved:x")
    assert _invalid(validator, bad)


def test_resolved_to_placeholder_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["edges"][0]["target"] = "unresolved:x"
    assert _invalid(validator, bad)


def test_parent_path_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["nodes"][0]["path"] = "../x.py"
    assert _invalid(validator, bad)


def test_schema_version_2_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["schema_version"] = 2
    assert _invalid(validator, bad)


def test_bad_snapshot_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["snapshot"] = "abc"
    assert _invalid(validator, bad)
