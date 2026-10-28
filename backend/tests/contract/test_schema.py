"""Schema v2 contract: serializer output is valid, and documents breaking a provenance rule are rejected."""

import copy

import pytest

from graphora.graph.model import (
    AssetNode,
    CoverageFile,
    Definition,
    Edge,
    Export,
    ExternalNode,
    FileNode,
    GraphDocument,
    UnresolvedNode,
)
from graphora.graph.serialize import to_dict

SNAP = "content:0123456789abcdef"
HASH = "sha256:0123456789abcdef"


@pytest.fixture
def doc():
    """A Python-only document: nodes[0] a.py, nodes[1] b.py, edges[0] a.py → b.py."""
    edge = Edge("file:a.py", "file:b.py", "f", 3, 1, SNAP, "resolved", None, "python-adapter@0.2.0", HASH)
    return to_dict(
        GraphDocument(
            snapshot=SNAP,
            extractors={"python-adapter": "0.2.0"},
            nodes=(FileNode("a.py", "python", (Definition("class", "C", 1),)), FileNode("b.py", "python")),
            edges=(edge,),
            files=(CoverageFile("a.py", "python", "analyzed"), CoverageFile("b.py", "python", "analyzed")),
            skipped=(),
        )
    )


@pytest.fixture
def ts_doc():
    """A TS document. Nodes by id: asset, ext:npm, file:a.ts, unresolved:npm. Edges: imports, reexports, unresolved."""
    extractor = "js-adapter@0.1.0"
    edges = (
        Edge("file:a.ts", "ext:npm:react", "default", 1, 1, SNAP, "resolved", None, extractor, HASH),
        Edge("file:a.ts", "asset:s.css", None, 2, 1, SNAP, "resolved", None, extractor, HASH),
        Edge("file:a.ts", "file:a.ts", "*", 3, 1, SNAP, "resolved", None, extractor, HASH, type="reexports", alias="ns"),
        Edge("file:a.ts", "unresolved:npm:./x", None, 4, 1, SNAP, "unresolved", "not_found", extractor, HASH),
    )
    return to_dict(
        GraphDocument(
            snapshot=SNAP,
            extractors={"js-adapter": "0.1.0"},
            nodes=(
                FileNode("a.ts", "typescript", (Definition("interface", "I", 1, ("I",)),), (Export("default", None, 5),)),
                ExternalNode("react", "npm", "third_party"),
                UnresolvedNode("./x", "npm"),
                AssetNode("s.css"),
            ),
            edges=edges,
            files=(CoverageFile("a.ts", "typescript", "analyzed"), CoverageFile("s.css", None, "not_code")),
            skipped=(),
        )
    )


def _node(doc, prefix):
    return next(n for n in doc["nodes"] if n["id"].startswith(prefix))


def _edge(doc, edge_type="imports", confidence="resolved"):
    return next(e for e in doc["edges"] if e["type"] == edge_type and e["confidence"] == confidence)


def test_python_document_valid(doc, validator):
    validator.validate(doc)


def test_ts_document_valid(ts_doc, validator):
    validator.validate(ts_doc)
    assert {n["kind"] for n in ts_doc["nodes"]} == {"asset", "external", "file", "unresolved"}


@pytest.mark.parametrize("field", ["snippet_hash", "form", "type_only"])
def test_edge_without_required_field_rejected(doc, validator, field):
    bad = copy.deepcopy(doc)
    del bad["edges"][0][field]
    assert not validator.is_valid(bad)


def test_alias_on_imports_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["edges"][0]["alias"] = "x"
    assert not validator.is_valid(bad)


def test_dynamic_reexport_rejected(ts_doc, validator):
    bad = copy.deepcopy(ts_doc)
    _edge(bad, "reexports")["form"] = "dynamic"
    assert not validator.is_valid(bad)


def test_unresolved_without_reason_rejected(ts_doc, validator):
    bad = copy.deepcopy(ts_doc)
    del _edge(bad, confidence="unresolved")["reason"]
    assert not validator.is_valid(bad)


def test_resolved_to_placeholder_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["edges"][0]["target"] = "unresolved:python:x"
    assert not validator.is_valid(bad)


def test_ts_file_without_exports_rejected(ts_doc, validator):
    bad = copy.deepcopy(ts_doc)
    del _node(bad, "file:")["exports"]
    assert not validator.is_valid(bad)


def test_ts_definition_without_exported_as_rejected(ts_doc, validator):
    bad = copy.deepcopy(ts_doc)
    del _node(bad, "file:")["definitions"][0]["exported_as"]
    assert not validator.is_valid(bad)


def test_python_definition_with_exported_as_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["nodes"][0]["definitions"][0]["exported_as"] = []
    assert not validator.is_valid(bad)


def test_python_interface_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["nodes"][0]["definitions"][0]["kind"] = "interface"
    assert not validator.is_valid(bad)


def test_python_file_with_exports_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["nodes"][0]["exports"] = []
    assert not validator.is_valid(bad)


def test_npm_stdlib_category_rejected(ts_doc, validator):
    bad = copy.deepcopy(ts_doc)
    _node(bad, "ext:")["category"] = "stdlib"
    assert not validator.is_valid(bad)


def test_ecosystem_id_mismatch_rejected(ts_doc, validator):
    bad = copy.deepcopy(ts_doc)
    _node(bad, "ext:").update(ecosystem="python", category="stdlib")
    assert not validator.is_valid(bad)


def test_v1_external_id_rejected(ts_doc, validator):
    bad = copy.deepcopy(ts_doc)
    _node(bad, "ext:")["id"] = "ext:react"
    assert not validator.is_valid(bad)


def test_unresolved_without_ecosystem_rejected(ts_doc, validator):
    bad = copy.deepcopy(ts_doc)
    del _node(bad, "unresolved:")["ecosystem"]
    assert not validator.is_valid(bad)


def test_schema_version_1_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["schema_version"] = 1
    assert not validator.is_valid(bad)


def test_parent_path_rejected(ts_doc, validator):
    bad = copy.deepcopy(ts_doc)
    _node(bad, "file:")["path"] = "../x.ts"
    assert not validator.is_valid(bad)


def test_bad_snapshot_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["snapshot"] = "abc"
    assert not validator.is_valid(bad)
