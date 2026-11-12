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


def test_csharp_projects_end_to_end(tmp_path, validator):
    """007 US2: project nodes, reference edges, visibility and a broken project file."""
    import json

    def write(path, text):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)

    write("Web/Web.csproj", '<Project Sdk="Microsoft.NET.Sdk.Web">\n  <ItemGroup>\n    <ProjectReference Include="..\\Core\\Core.csproj" />\n    <PackageReference Include="Serilog" />\n  </ItemGroup>\n</Project>\n')
    write("Core/Core.csproj", '<Project Sdk="Microsoft.NET.Sdk"></Project>\n')
    write("Bad/Bad.csproj", "<Project><ItemGroup>\n")
    write("Web/Home.cs", "using Core;\nusing Serilog.Events;\nusing Microsoft.AspNetCore.Mvc;\nclass Home {}\n")
    write("Core/Order.cs", "using Web;\nnamespace Core;\nclass Order {}\n")
    write("Bad/X.cs", "class X {}\n")
    analysis = analyze(tmp_path, 100, 1024 * 1024, Deadline(30))
    out = json.loads(dumps(analysis.doc))
    validator.validate(out)
    assert analysis.warnings == ("Bad/Bad.csproj",)
    assert {n["id"] for n in out["nodes"] if n["kind"] == "project"} == {"project:Bad/Bad.csproj", "project:Core/Core.csproj", "project:Web/Web.csproj"}
    edges = sorted((e["source"], e["line"], e["target"], e["type"], e["confidence"], e.get("reason")) for e in out["edges"])
    assert edges == [
        ("file:Core/Order.cs", 1, "unresolved:dotnet:Web", "imports", "unresolved", "not_found"),
        ("file:Web/Home.cs", 1, "file:Core/Order.cs", "imports", "resolved", None),
        ("file:Web/Home.cs", 2, "ext:nuget:Serilog", "imports", "heuristic", "package_prefix"),
        ("file:Web/Home.cs", 3, "ext:dotnet:Microsoft.AspNetCore.Mvc", "imports", "resolved", None),
        ("project:Web/Web.csproj", 3, "project:Core/Core.csproj", "project_reference", "resolved", None),
        ("project:Web/Web.csproj", 4, "ext:nuget:Serilog", "package_reference", "resolved", None),
    ]
    coverage = {f["path"]: f["flags"] for f in out["coverage"]["files"]}
    assert coverage["Bad/Bad.csproj"] == ["parse_error"]
    files = {n["path"]: n["project"] for n in out["nodes"] if n["kind"] == "file"}
    assert files == {"Bad/X.cs": "project:Bad/Bad.csproj", "Core/Order.cs": "project:Core/Core.csproj", "Web/Home.cs": "project:Web/Web.csproj"}


def test_csharp_type_references_end_to_end(tmp_path, validator):
    """008 US1: type-reference edges, the `using` fallback, ambiguity and the unresolved count."""
    import json

    def write(path, text):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)

    write("App/App.csproj", '<Project Sdk="Microsoft.NET.Sdk"></Project>\n')
    for name in ("Mailer", "Clock", "Queue"):
        write(f"App/Services/{name}.cs", f"namespace App.Services;\npublic class {name} {{ }}\n")
    write("App/Ext/Extensions.cs", "namespace App.Ext;\npublic static class Extensions { }\n")
    write("App/T1/Timer.cs", "namespace App.T1;\npublic class Timer { }\n")
    write("App/T2/Timer.cs", "namespace App.T2;\npublic class Timer { }\n")
    write(
        "App/Program.cs",
        "using App.Services;\nusing App.Ext;\nusing App.T1;\nusing App.T2;\nusing Serilog;\n"
        "namespace App;\nclass Program\n{\n    Mailer first;\n    Mailer again;\n    Timer t;\n    ILogger log;\n}\n",
    )
    out = json.loads(dumps(analyze(tmp_path, 100, 1024 * 1024, Deadline(30)).doc))
    validator.validate(out)
    edges = sorted(
        (e["line"], e["type"], e["target"], e["confidence"], e.get("reason"))
        for e in out["edges"]
        if e["source"] == "file:App/Program.cs"
    )
    assert edges == [
        (2, "imports", "file:App/Ext/Extensions.cs", "resolved", None),  # nothing used through it: fallback stays
        (3, "imports", "file:App/T1/Timer.cs", "resolved", None),  # ambiguous use is not a resolved one
        (4, "imports", "file:App/T2/Timer.cs", "resolved", None),
        (5, "imports", "unresolved:dotnet:Serilog", "unresolved", "not_found"),
        (9, "type_reference", "file:App/Services/Mailer.cs", "resolved", None),
        (11, "type_reference", "unresolved:dotnet:Timer", "unresolved", "ambiguous"),
    ]
    coverage = {f["path"]: f.get("unresolved_type_names") for f in out["coverage"]["files"]}
    assert coverage["App/Program.cs"] == 1  # ILogger
    assert coverage["App/App.csproj"] is None


def test_csharp_project_usings_end_to_end(tmp_path, validator):
    """008 US2: implicit usings, Directory.Build.props, <Using> items and global usings across files."""
    import json

    def write(path, text):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)

    write(
        "Directory.Build.props",
        '<Project>\n  <PropertyGroup><ImplicitUsings>enable</ImplicitUsings></PropertyGroup>\n'
        '  <ItemGroup Condition="\'$(X)\' == \'\'"><Using Include="Lib.Debug" /></ItemGroup>\n</Project>\n',
    )
    write("Lib/Lib.csproj", '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup><Using Include="Lib.Models" /></ItemGroup></Project>\n')
    write("Lib/Models/User.cs", "namespace Lib.Models;\npublic class User { }\n")
    write("Lib/Services/Mailer.cs", "namespace Lib.Services;\npublic class Mailer { }\n")
    write("Lib/Debug/Probe.cs", "namespace Lib.Debug;\npublic class Probe { }\n")
    write("Lib/GlobalUsings.cs", "global using Lib.Services;\n")
    write("Lib/Use.cs", "namespace Lib.Use;\nclass Use\n{\n    User u;\n    Mailer m;\n    Probe p;\n    List<Task> tasks;\n}\n")
    out = json.loads(dumps(analyze(tmp_path, 100, 1024 * 1024, Deadline(30)).doc))
    validator.validate(out)
    edges = sorted(
        (e["source"], e["line"], e["type"], e["target"], e["confidence"], e.get("reason")) for e in out["edges"]
    )
    assert edges == [
        ("file:Lib/Use.cs", 4, "type_reference", "file:Lib/Models/User.cs", "resolved", None),
        ("file:Lib/Use.cs", 5, "type_reference", "file:Lib/Services/Mailer.cs", "resolved", None),
        ("file:Lib/Use.cs", 6, "type_reference", "file:Lib/Debug/Probe.cs", "heuristic", "msbuild_condition"),
    ]  # the global using in GlobalUsings.cs was used, so its fallback edge is gone
    coverage = {f["path"]: f.get("unresolved_type_names") for f in out["coverage"]["files"]}
    assert coverage["Lib/Use.cs"] == 0  # List and Task come from the implicit usings
