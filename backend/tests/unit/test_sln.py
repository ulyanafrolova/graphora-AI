"""Solution files read as data (specs/009-csharp-solutions-project-views research § R1, R2)."""

import pytest

from graphora.adapters.msbuild.sln import read, read_sln, read_slnx

SLN = """﻿
Microsoft Visual Studio Solution File, Format Version 12.00
# Visual Studio Version 17
Project("{9A19103F-16F7-4668-BE54-9A1E7A4F7556}") = "Core", "src\\Core\\Core.csproj", "{11111111-1111-1111-1111-111111111111}"
EndProject
Project("{2150E333-8FDC-42A3-9474-1A3956D46DE8}") = "tests", "tests", "{22222222-2222-2222-2222-222222222222}"
	ProjectSection(SolutionItems) = preProject
		README.md = README.md
	EndProjectSection
EndProject
Project("{F2A71F9B-5D33-465A-A702-920D77279786}") = "Lib", "lib\\Lib.fsproj", "{33333333-3333-3333-3333-333333333333}"
EndProject
	Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Web", "src/Web/Web.csproj", "{44444444-4444-4444-4444-444444444444}"
EndProject
Global
EndGlobal
"""


def test_sln_entries_skip_folders():
    facts = read_sln(SLN.replace("\n", "\r\n").encode())
    assert not facts.has_error
    assert [(e.path, e.line, e.column) for e in facts.entries] == [
        ("src\\Core\\Core.csproj", 4, 1),
        ("lib\\Lib.fsproj", 11, 1),
        ("src/Web/Web.csproj", 13, 2),
    ]
    assert facts.entries[0].text.startswith('Project("{9A19103F')


@pytest.mark.parametrize("data", [b"Project(\"{X}\") = \"A\", \"A.csproj\", \"{Y}\"", b"\xff\xfe", b""])
def test_sln_without_header_or_not_utf8_is_an_error(data):
    assert read_sln(data).has_error


SLNX = """<Solution>
  <Folder Name="/src/">
    <Project Path="src/Core/Core.csproj" />
    <Project Path="src\\Web\\Web.csproj" Type="Classic C#" />
  </Folder>
  <Folder Name="/Solution Items/">
    <File Path="README.md" />
  </Folder>
  <Project Path="lib/Lib.fsproj" />
</Solution>
"""


def test_slnx_entries():
    facts = read_slnx(SLNX.encode())
    assert [(e.path, e.line, e.column) for e in facts.entries] == [
        ("src/Core/Core.csproj", 3, 5),
        ("src\\Web\\Web.csproj", 4, 5),
        ("lib/Lib.fsproj", 9, 3),
    ]
    assert facts.entries[1].text == '<Project Path="src\\Web\\Web.csproj" Type="Classic C#" />'


@pytest.mark.parametrize(
    "data",
    [
        b'<!DOCTYPE s [<!ENTITY a "x">]><Solution><Project Path="&a;.csproj" /></Solution>',
        b"<Solution><Project Path=",
    ],
)
def test_slnx_doctype_and_malformed(data):
    facts = read_slnx(data)
    assert facts.has_error and facts.entries == ()


def test_read_picks_the_format_by_extension():
    assert read("a/App.slnx", SLNX.encode()).entries[0].path == "src/Core/Core.csproj"
    assert read("App.sln", SLN.encode()).entries[0].path == "src\\Core\\Core.csproj"
