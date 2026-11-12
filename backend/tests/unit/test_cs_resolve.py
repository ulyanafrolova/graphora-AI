"""C# resolution (specs/007-csharp-analysis/data-model.md § Resolution, research R3–R6)."""

from pathlib import Path

import pytest

from graphora.adapters.csharp.extract import extract
from graphora.adapters.msbuild.csproj import read as read_csproj
from graphora.resolve.csharp import (
    NETCORE,
    Context,
    Projects,
    Resolver,
    Target,
    build_scopes,
    candidates,
    csproj_folders,
    framework_namespaces,
    namespaces_for,
    owner,
)

# --- ownership -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, expected",
    [
        ("src/App/Program.cs", ("src/App/App.csproj", False)),
        ("src/App/Deep/Er/X.cs", ("src/App/App.csproj", False)),
        ("src/App/Nested/N.cs", ("src/App/Nested/Nested.csproj", False)),
        ("two/X.cs", (None, True)),
        ("two/sub/Y.cs", (None, True)),
        ("loose/Z.cs", (None, False)),
        ("Root.cs", (None, False)),
    ],
)
def test_owner(path, expected):
    folders = csproj_folders(["src/App/App.csproj", "src/App/Nested/Nested.csproj", "two/A.csproj", "two/B.csproj"])
    assert owner(path, folders) == expected


def test_owner_at_root():
    assert owner("A/B.cs", csproj_folders(["Root.csproj"])) == ("Root.csproj", False)


# --- base-library list ------------------------------------------------------------------------------------------


def test_framework_list_shape():
    table = framework_namespaces()
    assert set(table) == {"Microsoft.AspNetCore.App", "Microsoft.NETCore.App", "Microsoft.WindowsDesktop.App"}
    assert {"System", "System.Linq", "System.Collections.Generic", "System.IO"} <= table[NETCORE]
    assert "Microsoft.AspNetCore.Mvc" not in table[NETCORE]
    assert "Microsoft.AspNetCore.Mvc" in table["Microsoft.AspNetCore.App"]


# --- candidates -------------------------------------------------------------------------------------------------


def _record(source):
    return extract(source.encode()).usings[0]


@pytest.mark.parametrize(
    "source, expected",
    [
        ("using X;", ("X",)),
        ("namespace A.B { using X.Y; }", ("A.B.X.Y", "A.X.Y", "X.Y")),
        ("namespace A { using global::X; }", ("X",)),
    ],
)
def test_candidates(source, expected):
    assert candidates(_record(source)) == expected


# --- using resolution in one scope ------------------------------------------------------------------------------

FILES = {
    "App/Program.cs": "namespace App { class Program {} }",
    "App/Services/Mailer.cs": "namespace App.Services { class Mailer {} }",
    "App/Services/Clock.cs": "namespace App.Services { class Clock {} }",
    "App/Services/Queue.cs": "namespace App.Services { class Queue {} }",
    "App/Models/User.cs": "namespace App.Models { public class User {} }",
    "App/Util/Strings.cs": "namespace App.Util { static class Strings {} }",
    "App/Parts/P1.cs": "namespace App.Parts { partial class P {} }",
    "App/Parts/P2.cs": "namespace App.Parts { partial class P {} }",
    "App/Deep/Only.cs": "namespace Outer.Inner { class Only {} }",
    "App/Rel/R.cs": "namespace Co.App.Services { class R {} }",
}


@pytest.fixture(scope="module")
def resolver():
    facts = {p: extract(s.encode()) for p, s in FILES.items()}
    return Resolver(build_scopes(facts, {p: "App/App.csproj" for p in FILES}))


CTX = Context(visible=(("App/App.csproj", False),), frameworks=namespaces_for([NETCORE]))


def _resolve(resolver, source, path="App/Program.cs", ctx=CTX):
    return resolver.resolve(path, _record(source), ctx)


def test_namespace_in_one_file_is_resolved(resolver):
    assert _resolve(resolver, "using App.Models;") == [Target("file:App/Models/User.cs", "App.Models", "resolved", None)]


def test_namespace_spread_over_files_is_heuristic(resolver):
    targets = _resolve(resolver, "using App.Services;")
    assert [t.node_id for t in targets] == ["file:App/Services/Clock.cs", "file:App/Services/Mailer.cs", "file:App/Services/Queue.cs"]
    assert {(t.confidence, t.reason) for t in targets} == {("heuristic", "namespace_spread")}


def test_no_edge_to_self(resolver):
    assert _resolve(resolver, "using App;") == []
    targets = _resolve(resolver, "using App.Services;", path="App/Services/Clock.cs")
    assert [t.node_id for t in targets] == ["file:App/Services/Mailer.cs", "file:App/Services/Queue.cs"]
    assert {t.reason for t in targets} == {"namespace_spread"}


def test_parent_only_namespace_is_no_types(resolver):
    assert _resolve(resolver, "using Outer;") == [Target("unresolved:dotnet:Outer", "Outer", "unresolved", "no_types")]


def test_base_library(resolver):
    assert _resolve(resolver, "using System.Collections.Generic;") == [
        Target("ext:dotnet:System.Collections.Generic", "System.Collections.Generic", "resolved", None)
    ]
    assert _resolve(resolver, "using global::System.IO;")[0].node_id == "ext:dotnet:System.IO"


def test_aspnetcore_namespace_needs_the_framework(resolver):
    assert _resolve(resolver, "using Microsoft.AspNetCore.Mvc;")[0].reason == "not_found"
    web = Context(CTX.visible, namespaces_for([NETCORE, "Microsoft.AspNetCore.App"]))
    assert _resolve(resolver, "using Microsoft.AspNetCore.Mvc;", ctx=web)[0].node_id == "ext:dotnet:Microsoft.AspNetCore.Mvc"


def test_not_found(resolver):
    assert _resolve(resolver, "using Missing.Namespace;") == [
        Target("unresolved:dotnet:Missing.Namespace", "Missing.Namespace", "unresolved", "not_found")
    ]


def test_relative_lookup_inside_namespace_block(resolver):
    targets = _resolve(resolver, "namespace Co.App { using Services; }")
    assert targets == [Target("file:App/Rel/R.cs", "Co.App.Services", "resolved", None)]


def test_relative_lookup_falls_back_to_the_written_name(resolver):
    targets = _resolve(resolver, "namespace Elsewhere { using App.Models; }")
    assert [t.node_id for t in targets] == ["file:App/Models/User.cs"]


def test_global_prefix_skips_relative_lookup(resolver):
    assert _resolve(resolver, "namespace Co.App { using global::Services; }")[0].reason == "not_found"


def test_using_static_to_one_file(resolver):
    assert _resolve(resolver, "using static App.Util.Strings;") == [Target("file:App/Util/Strings.cs", "App.Util.Strings", "resolved", None)]


def test_using_static_to_partial_type(resolver):
    targets = _resolve(resolver, "using static App.Parts.P;")
    assert [(t.node_id, t.reason) for t in targets] == [("file:App/Parts/P1.cs", "partial_type"), ("file:App/Parts/P2.cs", "partial_type")]


def test_using_static_of_base_library_type(resolver):
    assert _resolve(resolver, "using static System.Math;") == [Target("ext:dotnet:System", "System", "resolved", None)]


def test_type_alias_and_namespace_alias(resolver):
    assert _resolve(resolver, "using U = App.Models.User;") == [Target("file:App/Models/User.cs", "App.Models.User", "resolved", None)]
    assert [t.node_id for t in _resolve(resolver, "using M = App.Models;")] == ["file:App/Models/User.cs"]
    assert _resolve(resolver, "using L = System.Collections.Generic.List<int>;")[0].node_id == "ext:dotnet:System.Collections.Generic"


def test_alias_to_tuple_makes_no_edge(resolver):
    assert _resolve(resolver, "using P = (int, int);") == []


def test_global_using_resolves_like_file_level(resolver):
    assert [t.node_id for t in _resolve(resolver, "global using App.Models;")] == ["file:App/Models/User.cs"]


def test_reason_priority():
    from graphora.resolve.csharp import _reason

    assert _reason("msbuild_condition", "namespace_spread") == "namespace_spread"
    assert _reason(None, "msbuild_condition") == "msbuild_condition"
    assert _reason("package_prefix", "partial_type") == "partial_type"
    assert _reason(None, None) is None


# --- projects (T010: data-model.md § ProjectReference, § PackageReference, research R4) --------------------------


def _csproj(*items: str, sdk="Microsoft.NET.Sdk", extra="") -> bytes:
    body = "\n".join(f"    {i}" for i in items)
    return f'<Project Sdk="{sdk}">\n  {extra}\n  <ItemGroup>\n{body}\n  </ItemGroup>\n</Project>\n'.encode()


@pytest.fixture(scope="module")
def projects():
    return Projects(
        {
            "src/Web/Web.csproj": read_csproj(
                _csproj(
                    '<ProjectReference Include="..\\Core\\Core.csproj" />',
                    '<ProjectReference Include="../Missing/Missing.csproj" />',
                    '<ProjectReference Include="$(Root)\\X.csproj" />',
                    '<ProjectReference Include="..\\..\\..\\outside\\O.csproj" />',
                    '<ProjectReference Include="..\\Opt\\Opt.csproj" Condition="\'$(A)\' == \'1\'" />',
                    '<PackageReference Include="serilog" Version="3" />',
                    '<PackageReference Include="Foo" />',
                    '<PackageReference Include="Foo.Bar" />',
                    '<PackageReference Include="$(Pkg)" />',
                    sdk="Microsoft.NET.Sdk.Web",
                )
            ),
            "src/Core/Core.csproj": read_csproj(_csproj('<ProjectReference Include="..\\Base\\Base.csproj" />', '<PackageReference Include="Serilog" />')),
            "src/Base/Base.csproj": read_csproj(_csproj()),
            "src/Opt/Opt.csproj": read_csproj(_csproj()),
            "src/Desk/Desk.csproj": read_csproj(_csproj(extra="<PropertyGroup><UseWindowsForms>true</UseWindowsForms></PropertyGroup>")),
            "src/Lone/Lone.csproj": read_csproj(_csproj()),
        }
    )


def test_project_references(projects):
    assert [(t.node_id, t.confidence, t.reason) for t in projects.references["src/Web/Web.csproj"]] == [
        ("project:src/Core/Core.csproj", "resolved", None),
        ("unresolved:dotnet:src/Missing/Missing.csproj", "unresolved", "not_found"),
        ("unresolved:dotnet:$(Root)\\X.csproj", "unresolved", "msbuild_property"),
        ("unresolved:dotnet:..\\..\\..\\outside\\O.csproj", "unresolved", "not_found"),
        ("project:src/Opt/Opt.csproj", "heuristic", "msbuild_condition"),
    ]
    assert projects.references["src/Web/Web.csproj"][0].symbol == "..\\Core\\Core.csproj"


def test_package_references_keep_the_first_spelling(projects):
    assert [(t.node_id, t.confidence, t.reason) for t in projects.packages["src/Web/Web.csproj"]] == [
        ("ext:nuget:Serilog", "resolved", None),
        ("ext:nuget:Foo", "resolved", None),
        ("ext:nuget:Foo.Bar", "resolved", None),
        ("unresolved:dotnet:$(Pkg)", "unresolved", "msbuild_property"),
    ]
    assert [t.node_id for t in projects.packages["src/Core/Core.csproj"]] == ["ext:nuget:Serilog"]
    assert projects.packages["src/Web/Web.csproj"][0].symbol == "serilog"  # as written; node spelling from Core


def test_visibility_is_transitive_and_marks_conditional_paths(projects):
    assert projects.context("src/Web/Web.csproj").visible == (
        ("src/Web/Web.csproj", False),
        ("src/Base/Base.csproj", False),
        ("src/Core/Core.csproj", False),
        ("src/Opt/Opt.csproj", True),
    )
    assert projects.context("src/Lone/Lone.csproj").visible == (("src/Lone/Lone.csproj", False),)
    assert projects.context(None).visible == (("", False),)


def test_frameworks_depend_on_the_sdk(projects):
    assert "Microsoft.AspNetCore.Mvc" in projects.context("src/Web/Web.csproj").frameworks
    assert "Microsoft.AspNetCore.Mvc" not in projects.context("src/Core/Core.csproj").frameworks
    assert "System.Windows.Forms" in projects.context("src/Desk/Desk.csproj").frameworks
    assert "System.Linq" in projects.context(None).frameworks


SOURCES = {
    "src/Web/Home.cs": "namespace Web { class Home {} }",
    "src/Core/Order.cs": "namespace Core.Domain { class Order {} }",
    "src/Core/Line.cs": "namespace Core.Domain { class Line {} }",
    "src/Base/Id.cs": "namespace Base { class Id {} }",
    "src/Opt/Extra.cs": "namespace Opt { class Extra {} }",
    "src/Lone/Hidden.cs": "namespace Hidden { class H {} }",
}


@pytest.fixture(scope="module")
def multi(projects):
    from graphora.resolve.csharp import csproj_folders

    folders = csproj_folders(projects.paths)
    owners = {p: owner(p, folders)[0] for p in SOURCES}
    return Resolver(build_scopes({p: extract(s.encode()) for p, s in SOURCES.items()}, owners))


def _web(multi, projects, source):
    return multi.resolve("src/Web/Home.cs", _record(source), projects.context("src/Web/Web.csproj"))


def test_referenced_project_namespace(multi, projects):
    targets = _web(multi, projects, "using Core.Domain;")
    assert [(t.node_id, t.reason) for t in targets] == [("file:src/Core/Line.cs", "namespace_spread"), ("file:src/Core/Order.cs", "namespace_spread")]


def test_transitive_reference(multi, projects):
    assert _web(multi, projects, "using Base;") == [Target("file:src/Base/Id.cs", "Base", "resolved", None)]


def test_conditional_reference_downgrades(multi, projects):
    assert _web(multi, projects, "using Opt;") == [Target("file:src/Opt/Extra.cs", "Opt", "heuristic", "msbuild_condition")]


def test_unreferenced_project_is_not_referenced(multi, projects):
    assert _web(multi, projects, "using Hidden;") == [Target("unresolved:dotnet:Hidden", "Hidden", "unresolved", "not_referenced")]


def test_reference_is_one_way(multi, projects):
    targets = multi.resolve("src/Core/Order.cs", _record("using Web;"), projects.context("src/Core/Core.csproj"))
    assert targets[0].reason == "not_referenced"


def test_package_prefix(multi, projects):
    assert _web(multi, projects, "using Serilog.Events;") == [Target("ext:nuget:Serilog", "Serilog.Events", "heuristic", "package_prefix")]
    assert _web(multi, projects, "using serilog;")[0].node_id == "ext:nuget:Serilog"
    assert _web(multi, projects, "using SerilogX;")[0].reason == "not_found"


def test_ambiguous_package_prefix(multi, projects):
    assert _web(multi, projects, "using Foo.Bar.Baz;") == [Target("unresolved:dotnet:Foo.Bar.Baz", "Foo.Bar.Baz", "unresolved", "ambiguous")]
    assert _web(multi, projects, "using Foo.Other;")[0].node_id == "ext:nuget:Foo"


def test_package_through_type_alias(multi, projects):
    targets = _web(multi, projects, "using J = Serilog.Log;")
    assert targets == [Target("ext:nuget:Serilog", "Serilog.Log", "heuristic", "package_prefix")]


def test_base_library_wins_over_package_prefix(multi, projects):
    assert _web(multi, projects, "using Microsoft.AspNetCore.Mvc;")[0].node_id == "ext:dotnet:Microsoft.AspNetCore.Mvc"


# --- slice 2 data files (specs/008-csharp-type-references research R3, R4) ----------------------------------------

DATA = Path(__file__).resolve().parents[2] / "src" / "graphora" / "resolve" / "data"


def _data_lines(name):
    lines = (DATA / name).read_text(encoding="utf-8").split("\n")
    assert lines[-1] == ""
    return lines[0], lines[1:-1]


def test_dotnet_types_list():
    header, lines = _data_lines("dotnet_types.txt")
    assert header == "# dotnet-types@10.0.0"
    assert lines == sorted(set(lines))
    triples = {tuple(line.split(" ")) for line in lines}
    assert all(len(t) == 3 for t in triples)
    assert {
        ("Microsoft.NETCore.App", "System.Collections.Generic", "List"),
        ("Microsoft.NETCore.App", "System.Threading.Tasks", "Task"),
        ("Microsoft.AspNetCore.App", "Microsoft.AspNetCore.Mvc", "Controller"),
    } <= triples
    assert ("Microsoft.NETCore.App", "Microsoft.AspNetCore.Mvc", "Controller") not in triples
