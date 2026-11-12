"""005 research § R4, § R6: analyze() is build() plus the bytes it read; current_extractors() matches."""

from __future__ import annotations

import os

import pytest

from conftest import FIXTURES
from graphora.graph.build import analyze, build, current_extractors
from graphora.graph.serialize import dumps
from graphora.ingest.walk import Deadline

FIXTURE_NAMES = sorted(p.name for p in FIXTURES.iterdir() if (p / "repo").is_dir())


def _run(name: str):
    root = FIXTURES / name / "repo"
    return root, analyze(root, 5000, 50 * 1024 * 1024, Deadline(300)), build(root, 5000, 50 * 1024 * 1024, Deadline(300))


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_analyze_equals_build(name):
    _, analysis, (doc, warnings) = _run(name)
    assert dumps(analysis.doc) == dumps(doc)
    assert analysis.warnings == warnings


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_contents_are_the_bytes_on_disk(name):
    root, analysis, _ = _run(name)
    coverage = {f.path: f for f in analysis.doc.files}
    assert set(analysis.contents) <= set(coverage)
    for path, data in analysis.contents.items():
        assert data == (root / path).read_bytes(), path
    for path, entry in coverage.items():
        if path not in analysis.contents:
            assert "unreadable" in entry.flags, path


def test_unopenable_file_has_no_contents(tmp_path):
    (tmp_path / "a.py").write_text("import b\n")
    secret = tmp_path / "b.py"
    secret.write_text("x = 1\n")
    os.chmod(secret, 0)
    try:
        if os.access(secret, os.R_OK):
            pytest.skip("running as a user that ignores file permissions")
        analysis = analyze(tmp_path, 5000, 50 * 1024 * 1024, Deadline(300))
    finally:
        os.chmod(secret, 0o644)
    assert "b.py" not in analysis.contents
    assert "a.py" in analysis.contents


@pytest.mark.parametrize("name", ["py-flat", "ts-app", "mixed-fullstack"])
def test_current_extractors_match_documents(name):
    _, analysis, _ = _run(name)
    assert analysis.doc.extractors == current_extractors()


def test_csharp_folder_end_to_end(tmp_path, validator):
    """007: a small C# project gives file nodes with their project and `using` edges (data-model.md)."""
    (tmp_path / "App").mkdir()
    (tmp_path / "App" / "App.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"></Project>\n')
    (tmp_path / "App" / "Program.cs").write_text("using System.Linq;\nusing App.Models;\nusing Gone;\nnamespace App;\nclass Program {}\n")
    (tmp_path / "App" / "User.cs").write_text("namespace App.Models;\npublic record User(string Name);\n")
    (tmp_path / "Loose.cs").write_text("class Loose {}\n")
    doc, _ = build(tmp_path, 100, 1024 * 1024, Deadline(30))
    data = dumps(doc)
    import json

    out = json.loads(data)
    validator.validate(out)
    files = {n["path"]: n for n in out["nodes"] if n["kind"] == "file"}
    assert files["App/Program.cs"]["project"] == "project:App/App.csproj"
    assert files["Loose.cs"]["project"] is None
    assert files["App/User.cs"]["definitions"] == [{"kind": "record", "name": "App.Models.User", "line": 2}]
    edges = [(e["target"], e["confidence"], e["directive"], e["global_using"]) for e in out["edges"]]
    assert edges == [
        ("ext:dotnet:System.Linq", "resolved", "using", False),
        ("file:App/User.cs", "resolved", "using", False),
        ("unresolved:dotnet:Gone", "unresolved", "using", False),
    ]
    coverage = {f["path"]: (f["language"], f["status"]) for f in out["coverage"]["files"]}
    assert coverage["App/App.csproj"] == ("csharp", "not_code")
    assert coverage["App/Program.cs"] == ("csharp", "analyzed")
    assert set(out["extractors"]) >= {"csharp-adapter", "csharp-resolver", "dotnet-namespaces"}
