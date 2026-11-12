"""Reading .csproj files as data (specs/007-csharp-analysis research.md § R2)."""

import pytest

from graphora.adapters.msbuild.csproj import Item, read

SDK = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <UseWPF> True </UseWPF>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\\Core\\Core.csproj" />
    <PackageReference Include="Serilog" Version="3.1.1" />
    <PackageReference Update="Serilog" Version="4.0.0" />
    <FrameworkReference Include="Microsoft.AspNetCore.App" />
  </ItemGroup>
  <ItemGroup Condition="'$(Configuration)' == 'Debug'">
    <PackageReference Include="Debug.Tools" />
  </ItemGroup>
  <ItemGroup>
    <ProjectReference Include="a.csproj;b.csproj" Condition="'$(X)' == ''" />
    <Compile Remove="Old/**" />
  </ItemGroup>
  <Import Project="evil.targets" />
</Project>
"""


def test_items_sdk_and_flags():
    facts = read(SDK.encode())
    assert not facts.has_error
    assert (facts.sdk, facts.use_wpf, facts.use_windows_forms) == ("Microsoft.NET.Sdk.Web", True, False)
    assert [(i.kind, i.include, i.conditional, i.line, i.column) for i in facts.items] == [
        ("ProjectReference", "..\\Core\\Core.csproj", False, 7, 5),
        ("PackageReference", "Serilog", False, 8, 5),
        ("FrameworkReference", "Microsoft.AspNetCore.App", False, 10, 5),
        ("PackageReference", "Debug.Tools", True, 13, 5),
        ("ProjectReference", "a.csproj", True, 16, 5),
        ("ProjectReference", "b.csproj", True, 16, 5),
    ]
    assert facts.items[1].text == '<PackageReference Include="Serilog" Version="3.1.1" />'


def test_items_in_choose_when_are_conditional():
    data = b"""<Project><Choose><When Condition="true"><ItemGroup>
<PackageReference Include="A" /></ItemGroup></When></Choose></Project>"""
    assert read(data).items[0].conditional


def test_multi_line_start_tag_text():
    data = b'<Project>\n  <ItemGroup>\n    <PackageReference\n        Include="A"\n        Version="1" />\n  </ItemGroup>\n</Project>'
    item = read(data).items[0]
    assert (item.line, item.column) == (3, 5)
    assert item.text == '<PackageReference\n        Include="A"\n        Version="1" />'


def test_old_style_namespaced_project():
    data = b"""<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="15.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemGroup>
    <ProjectReference Include="..\\Lib\\Lib.csproj">
      <Project>{0000}</Project>
    </ProjectReference>
  </ItemGroup>
</Project>"""
    facts = read(data)
    assert [(i.kind, i.include) for i in facts.items] == [("ProjectReference", "..\\Lib\\Lib.csproj")]
    assert facts.sdk is None


def test_bom_crlf_and_non_ascii_column():
    data = '﻿<Project>\r\n<ItemGroup>\r\n<!-- é -->  <PackageReference Include="Ü" />\r\n</ItemGroup></Project>'.encode()
    item = read(data).items[0]
    assert (item.include, item.line, item.column) == ("Ü", 3, 13)


def test_items_outside_item_group_ignored():
    assert read(b'<Project><PackageReference Include="A" /></Project>').items == ()


@pytest.mark.parametrize(
    "data",
    [
        b'<?xml version="1.0"?>\n<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>\n<Project>&lol2;</Project>',
        b'<!DOCTYPE Project SYSTEM "file:///etc/passwd"><Project/>',
        b"<Project><ItemGroup>",
        b"not xml at all",
        b"<Project>\xff</Project>",
    ],
)
def test_refused_or_malformed(data):
    facts = read(data)
    assert facts.has_error and facts.items == ()


def test_item_is_a_value_object():
    assert Item("PackageReference", "A", False, 1, 1, "<x>") == Item("PackageReference", "A", False, 1, 1, "<x>")
