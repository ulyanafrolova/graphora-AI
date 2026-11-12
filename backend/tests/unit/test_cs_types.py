"""C# type-reference lookup (specs/008-csharp-type-references data-model.md § Resolution of a type reference)."""

import pytest

from graphora.adapters.csharp.extract import extract
from graphora.adapters.msbuild.csproj import read as read_csproj
from graphora.resolve.csharp import (
    NETCORE,
    Context,
    FileUsings,
    GlobalUsing,
    Projects,
    Resolver,
    Target,
    TypeResolver,
    build_scopes,
    directive_id,
    global_directives,
    namespaces_for,
    types_for,
)

REPO = {
    "App/Services/Mailer.cs": "namespace App.Services { public class Mailer { } }",
    "App/Services/Clock.cs": "namespace App.Services { public class Clock { } }",
    "App/Settings.cs": "namespace App { public class Settings { public class Inner { } } }",
    "App/Models/User.cs": "namespace App.Models { public partial class User { } }",
    "App/Models/User.Rules.cs": "namespace App.Models { public partial class User { } }",
    "App/Timers/Timer.cs": "namespace App.Timers { public class Timer { } }",
    "App/Other/Timer.cs": "namespace App.Other { public class Timer { } }",
    "App/Tasks/Task.cs": "namespace App.Tasks { public class Task { } }",
    "App/Checks/MyCheckAttribute.cs": "namespace App.Checks { public class MyCheckAttribute { } }",
    "Opt/Extra.cs": "namespace Opt { public class Extra { } }",
}


@pytest.fixture(scope="module")
def types():
    facts = {p: extract(s.encode()) for p, s in REPO.items()}
    owners = {p: ("Opt/Opt.csproj" if p.startswith("Opt/") else "App/App.csproj") for p in REPO}
    return TypeResolver(Resolver(build_scopes(facts, owners)))


CTX = Context(
    visible=(("App/App.csproj", False), ("Opt/Opt.csproj", True)),
    frameworks=namespaces_for([NETCORE]),
    library=types_for((NETCORE,)),
)


def _resolve(types, source, path="App/Program.cs", project=(), ctx=CTX):
    facts = extract(source.encode())
    usings = FileUsings(path, facts.usings, project)
    return [types.resolve(path, ref, ctx, usings) for ref in facts.type_refs if ref.kind != "qualifier"]


def _one(types, source, **kw):
    (result,) = _resolve(types, source, **kw)
    return result


def test_imported_namespace_one_file(types):
    r = _one(types, "using App.Services;\nclass P { Mailer m; }")
    assert r.targets == (Target("file:App/Services/Mailer.cs", "App.Services.Mailer", "resolved", None),)
    assert r.via == ("App/Program.cs:1:1",)


def test_same_namespace_without_using(types):
    r = _one(types, "namespace App.Services { class X { Clock c; } }", path="App/Services/X.cs")
    assert [t.node_id for t in r.targets] == ["file:App/Services/Clock.cs"] and r.via == ()


def test_enclosing_namespace_without_using(types):
    r = _one(types, "namespace App.Web.Controllers { class H { Settings s; } }")
    assert [t.node_id for t in r.targets] == ["file:App/Settings.cs"]


def test_enclosing_namespace_wins_over_import(types):
    r = _one(types, "using App.Other;\nnamespace App.Timers { class X { Timer t; } }")
    assert [t.node_id for t in r.targets] == ["file:App/Timers/Timer.cs"]


def test_ambiguous_imports(types):
    r = _one(types, "using App.Timers;\nusing App.Other;\nclass X { Timer t; }")
    assert r.targets == (Target("unresolved:dotnet:Timer", "Timer", "unresolved", "ambiguous"),) and r.via == ()


def test_ambiguous_with_base_library(types):
    r = _one(types, "using System.Threading.Tasks;\nusing App.Tasks;\nclass X { Task t; }")
    assert r.targets[0].reason == "ambiguous"


def test_base_library_type_has_no_edge(types):
    r = _one(types, "using System.Collections.Generic;\nclass X { List<int> xs; }")
    assert (r.targets, r.found) == ((), True)


def test_unknown_name_is_not_found(types):
    assert _one(types, "using Serilog;\nclass X { ILogger l; }").found is False


def test_partial_type(types):
    r = _one(types, "class X { App.Models.User u; }")
    assert [(t.node_id, t.reason) for t in r.targets] == [
        ("file:App/Models/User.Rules.cs", "partial_type"),
        ("file:App/Models/User.cs", "partial_type"),
    ]


def test_fully_qualified_and_rooted(types):
    assert [t.node_id for t in _one(types, "class X { App.Settings s; }").targets] == ["file:App/Settings.cs"]
    assert [t.node_id for t in _one(types, "class X { global::App.Settings s; }").targets] == ["file:App/Settings.cs"]
    assert _one(types, "namespace App { class X { global::Settings s; } }").found is False


def test_nested_type_through_using_and_enclosing(types):
    assert [t.node_id for t in _one(types, "using App;\nclass X { Settings.Inner i; }").targets] == ["file:App/Settings.cs"]
    assert [t.node_id for t in _one(types, "namespace App.Web { class X { Settings.Inner i; } }").targets] == ["file:App/Settings.cs"]


def test_alias_and_alias_qualifier(types):
    r = _one(types, "using U = App.Models.User;\nclass X { U u; }")
    assert len(r.targets) == 2 and r.via == ("App/Program.cs:1:1",)
    r = _one(types, "using S = App.Settings;\nclass X { S.Inner i; }")
    assert [t.node_id for t in r.targets] == ["file:App/Settings.cs"]


def test_attribute_suffix(types):
    r = _one(types, "using App.Checks;\n[MyCheck] class X { }")
    assert [t.node_id for t in r.targets] == ["file:App/Checks/MyCheckAttribute.cs"]


def test_conditional_visibility(types):
    r = _one(types, "using Opt;\nclass X { Extra e; }")
    assert r.targets == (Target("file:Opt/Extra.cs", "Opt.Extra", "heuristic", "msbuild_condition"),)


def test_self_reference_has_no_edge(types):
    r = _one(types, "namespace App.Services { class Mailer { Mailer next; } }", path="App/Services/Mailer.cs")
    assert (r.targets, r.found) == ((), True)


def test_using_inside_namespace_block_applies_at_its_level(types):
    r = _one(types, "namespace Elsewhere {\n  using App.Services;\n  class X { Mailer m; }\n}")
    assert [t.node_id for t in r.targets] == ["file:App/Services/Mailer.cs"] and r.via == ("App/Program.cs:2:3",)


def test_project_global_usings_and_conditional_ones(types):
    project = (GlobalUsing("item:App/App.csproj:5", "App.Services", conditional=True),)
    r = _one(types, "class X { Mailer m; }", project=project)
    assert r.targets == (Target("file:App/Services/Mailer.cs", "App.Services.Mailer", "heuristic", "msbuild_condition"),)
    assert r.via == ("item:App/App.csproj:5",)
    alias = (GlobalUsing("item:App/App.csproj:6", "App.Settings", alias="Cfg"),)
    assert [t.node_id for t in _one(types, "class X { Cfg c; }", project=alias).targets] == ["file:App/Settings.cs"]


def test_directive_id():
    record = extract(b"\n  using A;").usings[0]
    assert directive_id("a.cs", record) == "a.cs:2:3"


# --- project-wide usings (data-model.md § Project usings, research R4, R5) --------------------------------------


def _project(sdk="Microsoft.NET.Sdk", body=""):
    return read_csproj(f'<Project Sdk="{sdk}">{body}</Project>'.encode())


PROPS = read_csproj(
    b"""<Project>
  <PropertyGroup><ImplicitUsings>enable</ImplicitUsings></PropertyGroup>
  <ItemGroup><Using Include="App.Shared" /></ItemGroup>
  <ItemGroup Condition="'$(X)' == ''"><Using Include="App.Debug" /></ItemGroup>
</Project>"""
)


def _namespaces(usings):
    return [(g.origin.split(":")[0], g.namespace, g.alias, g.conditional) for g in usings]


def test_props_apply_to_projects_below_them():
    projects = Projects(
        {
            "src/Web/Web.csproj": _project("Microsoft.NET.Sdk.Web", '<ItemGroup><Using Remove="System.Net.Http" /><Using Include="App.Models.User" Alias="U" /></ItemGroup>'),
            "src/Worker/Worker.csproj": _project("Microsoft.NET.Sdk.Worker"),
            "other/Lib/Lib.csproj": _project(),
        },
        {"src/Directory.Build.props": PROPS},
    )
    assert projects.props_for("src/Web/Web.csproj") == "src/Directory.Build.props"
    assert projects.props_for("other/Lib/Lib.csproj") is None
    web = projects.global_usings("src/Web/Web.csproj")
    names = [g.namespace for g in web if g.alias is None]
    assert "System.Net.Http" not in names
    assert {"System", "Microsoft.AspNetCore.Builder", "App.Shared", "App.Debug"} <= set(names)
    assert ("item", "App.Models.User", "U", False) in _namespaces(web)
    assert ("item", "App.Debug", None, True) in _namespaces(web)
    worker = [g.namespace for g in projects.global_usings("src/Worker/Worker.csproj")]
    assert "Microsoft.Extensions.Hosting" in worker and "Microsoft.AspNetCore.Builder" not in worker
    assert projects.global_usings("other/Lib/Lib.csproj") == ()


def test_project_value_overrides_props_and_msbuild_values_are_ignored():
    off = _project(body="<PropertyGroup><ImplicitUsings>disable</ImplicitUsings></PropertyGroup>")
    prop = _project(body="<PropertyGroup><ImplicitUsings>$(Inherit)</ImplicitUsings></PropertyGroup><ItemGroup><Using Include=\"$(Ns)\" /></ItemGroup>")
    projects = Projects({"a/A.csproj": off, "b/B.csproj": prop}, {"Directory.Build.props": PROPS})
    assert [g.namespace for g in projects.global_usings("a/A.csproj")] == ["App.Shared", "App.Debug"]
    assert [g.namespace for g in projects.global_usings("b/B.csproj")] == ["App.Shared", "App.Debug"]


def test_conditional_implicit_usings():
    cond = read_csproj(b"""<Project><PropertyGroup Condition="'$(A)' == ''"><ImplicitUsings>true</ImplicitUsings></PropertyGroup></Project>""")
    usings = Projects({"A.csproj": cond}).global_usings("A.csproj")
    assert usings and all(g.conditional for g in usings)


def test_global_directives_and_project_less_files():
    records = extract(b"global using App.Services;\nglobal using static System.Math;\nglobal using M = App.Models;\nusing Local;").usings
    directives = global_directives("G.cs", records)
    assert [(g.origin, g.namespace, g.alias) for g in directives] == [
        ("G.cs:1:1", "App.Services", None),
        ("G.cs:3:1", "App.Models", "M"),
    ]
    assert Projects({}).global_usings(None, directives) == tuple(directives)


def test_global_directive_applies_to_another_file(types):
    project = tuple(global_directives("App/GlobalUsings.cs", extract(b"global using App.Services;").usings))
    r = _one(types, "class X { Mailer m; }", project=project)
    assert [t.node_id for t in r.targets] == ["file:App/Services/Mailer.cs"] and r.via == ("App/GlobalUsings.cs:1:1",)
