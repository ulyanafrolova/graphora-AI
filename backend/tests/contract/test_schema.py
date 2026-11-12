"""Schema v5 contract: serializer output is valid, and documents breaking a provenance rule are rejected."""

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
    ProjectNode,
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


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_old_schema_version_rejected(doc, validator, version):
    bad = copy.deepcopy(doc)
    bad["schema_version"] = version
    assert not validator.is_valid(bad)


def test_unreadable_dir_skip_reason_accepted(doc, validator):
    ok = copy.deepcopy(doc)
    ok["coverage"]["skipped"] = [{"path": "locked", "reason": "unreadable_dir"}]
    assert validator.is_valid(ok)


def test_parent_path_rejected(ts_doc, validator):
    bad = copy.deepcopy(ts_doc)
    _node(bad, "file:")["path"] = "../x.ts"
    assert not validator.is_valid(bad)


def test_bad_snapshot_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["snapshot"] = "abc"
    assert not validator.is_valid(bad)


# --- v4: C# (specs/007-csharp-analysis/contracts/graph.schema.json) ------------------------------------------


@pytest.fixture
def cs_doc():
    """A C# document. Edges by index: 0 spread using, 1 static, 2 global BCL, 3 alias, 4 unresolved, 5 project
    reference, 6 conditional package reference."""
    a, r = "csharp-adapter@0.1.0", "csproj-reader@0.1.0"
    p = "project:App/App.csproj"

    def using(target, line, confidence="resolved", reason=None, **extra):
        extra.setdefault("directive", "using")
        extra.setdefault("global_using", False)
        return Edge("file:App/P.cs", target, "App.S", line, 1, SNAP, confidence, reason, a, HASH, **extra)

    edges = (
        using("file:App/M.cs", 1, "heuristic", "namespace_spread"),
        using("file:App/U.cs", 2, directive="using_static"),
        using("ext:dotnet:System.Linq", 3, global_using=True),
        using("file:App/X.cs", 4, directive="using_alias", alias="J"),
        using("unresolved:dotnet:Missing", 5, "unresolved", "not_found"),
        Edge(p, "project:Core/Core.csproj", "..\\Core\\Core.csproj", 7, 5, SNAP, "resolved", None, r, HASH, type="project_reference"),
        Edge(p, "ext:nuget:Serilog", "Serilog", 8, 5, SNAP, "heuristic", "msbuild_condition", r, HASH, type="package_reference"),
    )
    return to_dict(
        GraphDocument(
            snapshot=SNAP,
            extractors={"csharp-adapter": "0.1.0", "csproj-reader": "0.1.0"},
            nodes=(
                FileNode("App/P.cs", "csharp", (Definition("record", "App.R", 3), Definition("method", "App.P.Main", 5)), None, p),
                FileNode("Loose.cs", "csharp"),
                ProjectNode("App/App.csproj"),
                ExternalNode("System.Linq", "dotnet", "stdlib"),
                ExternalNode("Serilog", "nuget", "third_party"),
                UnresolvedNode("Missing", "dotnet"),
            ),
            edges=edges,
            files=(CoverageFile("Loose.cs", "csharp", "analyzed", ("ambiguous_project",)),),
            skipped=(),
        )
    )


def _cs_edge(doc, line):
    return next(e for e in doc["edges"] if e["line"] == line)


def test_cs_document_valid(cs_doc, validator):
    validator.validate(cs_doc)


def _set(path_fn, **values):
    return lambda d: path_fn(d).update(values)


def _drop(path_fn, key):
    return lambda d: path_fn(d).pop(key)


CS_INVALID = {
    "heuristic without reason": _drop(lambda d: _cs_edge(d, 1), "reason"),
    "heuristic with unresolved reason": _set(lambda d: _cs_edge(d, 1), reason="not_found"),
    "unresolved with heuristic reason": _set(lambda d: _cs_edge(d, 5), reason="partial_type"),
    "directive without global_using": _drop(lambda d: _cs_edge(d, 1), "global_using"),
    "global_using without directive": _drop(lambda d: _cs_edge(d, 1), "directive"),
    "using_alias without alias": _drop(lambda d: _cs_edge(d, 4), "alias"),
    "alias on plain using": _set(lambda d: _cs_edge(d, 1), alias="X"),
    "project_reference from file": _set(lambda d: _cs_edge(d, 7), source="file:App/P.cs"),
    "package_reference to npm": _set(lambda d: _cs_edge(d, 8), target="ext:npm:serilog"),
    "imports from project": _set(lambda d: _cs_edge(d, 1), source="project:App/App.csproj"),
    "directive on project edge": _set(lambda d: _cs_edge(d, 7), directive="using", global_using=False),
    "csharp file without project": _drop(lambda d: _node(d, "file:App/P.cs"), "project"),
    "csharp file with exports": _set(lambda d: _node(d, "file:App/P.cs"), exports=[]),
    "csharp type_alias": lambda d: _node(d, "file:App/P.cs")["definitions"][0].update(kind="type_alias"),
    "ts file with project": _set(lambda d: _node(d, "file:Loose.cs"), language="typescript", exports=[]),
    "dotnet third_party": _set(lambda d: _node(d, "ext:dotnet:"), category="third_party"),
    "nuget stdlib": _set(lambda d: _node(d, "ext:nuget:"), category="stdlib"),
    "nuget placeholder": _set(lambda d: _node(d, "unresolved:"), id="unresolved:nuget:Missing", ecosystem="nuget"),
    "project node not a csproj": _set(lambda d: _node(d, "project:"), id="project:App/App.sln", path="App/App.sln"),
    "unknown coverage flag": lambda d: d["coverage"]["files"][0]["flags"].append("ambiguous"),
}


@pytest.mark.parametrize("case", sorted(CS_INVALID))
def test_cs_invalid_rejected(cs_doc, validator, case):
    bad = copy.deepcopy(cs_doc)
    CS_INVALID[case](bad)
    assert not validator.is_valid(bad)


def test_python_record_rejected(doc, validator):
    bad = copy.deepcopy(doc)
    bad["nodes"][0]["definitions"][0]["kind"] = "record"
    assert not validator.is_valid(bad)


# --- v5: C# type references (specs/008-csharp-type-references/contracts/graph.schema.json) -----------------------


@pytest.fixture
def types_doc(cs_doc):
    """cs_doc plus a resolved, a partial and an ambiguous type reference, and an unresolved-type-name count."""
    doc = copy.deepcopy(cs_doc)
    base = {k: v for k, v in _cs_edge(doc, 2).items() if k not in ("directive", "global_using")}
    doc["edges"] += [
        dict(base, type="type_reference", line=20, symbol="App.U"),
        dict(base, type="type_reference", line=21, target="file:App/M.cs", confidence="heuristic", reason="partial_type", symbol="App.M"),
        dict(base, type="type_reference", line=22, target="unresolved:dotnet:Missing", confidence="unresolved", reason="ambiguous", symbol="Missing"),
    ]
    doc["coverage"]["files"][0]["unresolved_type_names"] = 2
    return doc


def _ref(doc, line):
    return next(e for e in doc["edges"] if e["type"] == "type_reference" and e["line"] == line)


def test_types_document_valid(types_doc, validator):
    validator.validate(types_doc)


TYPES_INVALID = {
    "type_reference with directive": lambda d: _ref(d, 20).update(directive="using", global_using=False),
    "type_reference with alias": lambda d: _ref(d, 20).update(alias="X"),
    "type_reference to external": lambda d: _ref(d, 20).update(target="ext:dotnet:System.Linq"),
    "type_reference from project": lambda d: _ref(d, 20).update(source="project:App/App.csproj"),
    "type_reference to npm placeholder": lambda d: _ref(d, 22).update(target="unresolved:npm:Missing"),
    "count on a python file": lambda d: d["coverage"]["files"][0].update(language="python"),
    "count on a project file": lambda d: d["coverage"]["files"][0].update(path="App/App.csproj", status="not_code"),
    "negative count": lambda d: d["coverage"]["files"][0].update(unresolved_type_names=-1),
    "v4 document": lambda d: d.update(schema_version=4),
}


@pytest.mark.parametrize("case", sorted(TYPES_INVALID))
def test_types_invalid_rejected(types_doc, validator, case):
    bad = copy.deepcopy(types_doc)
    TYPES_INVALID[case](bad)
    assert not validator.is_valid(bad)
