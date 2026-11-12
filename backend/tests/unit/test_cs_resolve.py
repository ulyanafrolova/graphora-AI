"""C# resolution (specs/007-csharp-analysis/data-model.md § Resolution, research R3–R6)."""

import pytest

from graphora.adapters.csharp.extract import extract
from graphora.resolve.csharp import (
    NETCORE,
    Context,
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
