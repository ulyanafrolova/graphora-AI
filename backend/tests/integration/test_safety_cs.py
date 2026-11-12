"""Constitution Principle I for C#: project files are data, nothing is executed, nothing outside is read
(specs/007-csharp-analysis research.md § R2, SC-007)."""

import builtins
import json
import os
import shutil
import subprocess
import time

from conftest import FIXTURES, run_analyze


def _tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def _forbid(*_args, **_kwargs):
    raise AssertionError("analysis must not start a process")


def _no_processes(monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", _forbid)
    monkeypatch.setattr(os, "system", _forbid)
    for name in ("posix_spawn", "posix_spawnp", "execv", "execve", "execvp", "fork"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, _forbid)


def _record_opens(monkeypatch):
    opened: list[str] = []
    real_open, real_os_open = builtins.open, os.open

    def tracking_open(file, *args, **kwargs):
        opened.append(os.fspath(file) if not isinstance(file, int) else "")
        return real_open(file, *args, **kwargs)

    def tracking_os_open(path, *args, **kwargs):
        opened.append(os.fspath(path))
        return real_os_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", tracking_open)
    monkeypatch.setattr(os, "open", tracking_os_open)
    return opened


def test_project_files_are_data(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "X.csproj").write_text('<Project><ItemGroup><PackageReference Include="FromOutside" /></ItemGroup></Project>\n')
    (outside / "Secret.cs").write_text("namespace Secret { class S {} }\n")
    root = tmp_path / "repo"
    (root / "App").mkdir(parents=True)
    (root / "App" / "App.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        '  <Import Project="..\\..\\outside\\X.csproj" />\n'
        '  <Target Name="Evil" BeforeTargets="Build"><Exec Command="touch MARKER" /></Target>\n'
        "  <ItemGroup>\n"
        '    <ProjectReference Include="..\\..\\outside\\X.csproj" />\n'
        "  </ItemGroup>\n"
        "</Project>\n"
    )
    (root / "App" / "P.cs").write_text("using Secret;\nclass P {}\n")
    (root / "Bomb").mkdir()
    lol = "".join(f'<!ENTITY l{i} "{"".join(f"&l{i - 1};" for _ in range(10))}">' for i in range(1, 10))
    (root / "Bomb" / "Bomb.csproj").write_text(f'<?xml version="1.0"?>\n<!DOCTYPE b [<!ENTITY l0 "lol">{lol}]>\n<Project>&l9;</Project>\n')
    (root / "Ext").mkdir()
    (root / "Ext" / "Ext.csproj").write_text(f'<!DOCTYPE p [<!ENTITY x SYSTEM "file://{outside / "Secret.cs"}">]>\n<Project>&x;</Project>\n')
    before = _tree(root)

    _no_processes(monkeypatch)
    opened = _record_opens(monkeypatch)
    start = time.monotonic()
    code, out, err = run_analyze(root)
    elapsed = time.monotonic() - start

    assert code == 0, err
    assert elapsed < 1.0
    assert _tree(root) == before
    assert not (root / "App" / "MARKER").exists()
    assert not [p for p in opened if p.startswith(str(outside))]
    doc = json.loads(out)
    edges = {(e["source"], e["line"]): e for e in doc["edges"]}
    assert edges[("project:App/App.csproj", 5)]["reason"] == "not_found"
    assert edges[("file:App/P.cs", 1)]["target"] == "unresolved:dotnet:Secret"
    assert not [n for n in doc["nodes"] if "FromOutside" in n["id"]]
    flags = {f["path"]: f["flags"] for f in doc["coverage"]["files"]}
    assert flags["Bomb/Bomb.csproj"] == flags["Ext/Ext.csproj"] == ["parse_error"]


def test_csharp_edge_fixture_reads_only_its_own_files(tmp_path, monkeypatch):
    root = tmp_path / "copy"
    shutil.copytree(FIXTURES / "csharp-edge" / "repo", root)
    _no_processes(monkeypatch)
    code, out, err = run_analyze(root)
    assert code == 0, err
    assert "Injected" not in {n["id"].rsplit(":", 1)[-1] for n in json.loads(out)["nodes"] if n["kind"] == "external"}


def test_directory_build_props_are_data(tmp_path, monkeypatch):
    """008 research R5: Directory.Build.props is read as data; imports and $(…) are never followed."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.props").write_text('<Project><ItemGroup><Using Include="Secret" /></ItemGroup></Project>\n')
    (outside / "Secret.cs").write_text("namespace Secret { public class Leak { } }\n")
    root = tmp_path / "repo"
    (root / "safe" / "App").mkdir(parents=True)
    (root / "safe" / "Directory.Build.props").write_text(
        '<Project>\n  <Import Project="..\\..\\outside\\x.props" />\n'
        '  <ItemGroup><Using Include="$(Injected)" /></ItemGroup>\n</Project>\n'
    )
    (root / "safe" / "App" / "App.csproj").write_text("<Project />\n")
    (root / "safe" / "App" / "P.cs").write_text("class P { Leak l; }\n")
    (root / "bomb" / "B").mkdir(parents=True)
    lol = "".join(f'<!ENTITY l{i} "{"".join(f"&l{i - 1};" for _ in range(10))}">' for i in range(1, 10))
    (root / "bomb" / "Directory.Build.props").write_text(f'<!DOCTYPE b [<!ENTITY l0 "x">{lol}]>\n<Project>&l9;</Project>\n')
    (root / "bomb" / "B" / "B.csproj").write_text("<Project />\n")
    (root / "bomb" / "B" / "Q.cs").write_text("class Q { }\n")

    _no_processes(monkeypatch)
    opened = _record_opens(monkeypatch)
    start = time.monotonic()
    code, out, err = run_analyze(root)
    assert code == 0, err
    assert time.monotonic() - start < 1.0
    assert not [p for p in opened if p.startswith(str(outside))]
    doc = json.loads(out)
    assert [e for e in doc["edges"] if e["type"] == "type_reference"] == []  # `Leak` stays unknown
    coverage = {f["path"]: f for f in doc["coverage"]["files"]}
    assert coverage["safe/App/P.cs"]["unresolved_type_names"] == 1
    assert coverage["bomb/Directory.Build.props"]["flags"] == ["parse_error"]
    assert "ignoring bomb/Directory.Build.props" in err


def test_solution_files_are_data(tmp_path, monkeypatch):
    """009 research R1–R3: solution files are read as data; entries outside the root are never read."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "X.csproj").write_text('<Project><ItemGroup><PackageReference Include="FromOutside" /></ItemGroup></Project>\n')
    root = tmp_path / "repo"
    root.mkdir()
    (root / "App.sln").write_text(
        "Microsoft Visual Studio Solution File, Format Version 12.00\n"
        'Project("{9A19103F-16F7-4668-BE54-9A1E7A4F7556}") = "X", "..\\outside\\X.csproj", "{1}"\nEndProject\n'
    )
    lol = "".join(f'<!ENTITY l{i} "{"".join(f"&l{i - 1};" for _ in range(10))}">' for i in range(1, 10))
    (root / "Bomb.slnx").write_text(f'<!DOCTYPE s [<!ENTITY l0 "x">{lol}]>\n<Solution><Project Path="&l9;" /></Solution>\n')
    (root / "P.cs").write_text("class P { }\n")

    _no_processes(monkeypatch)
    opened = _record_opens(monkeypatch)
    start = time.monotonic()
    code, out, err = run_analyze(root)
    assert code == 0, err
    assert time.monotonic() - start < 1.0
    assert not [p for p in opened if p.startswith(str(outside))]
    doc = json.loads(out)
    member = next(e for e in doc["edges"] if e["type"] == "solution_member")
    assert (member["confidence"], member["reason"]) == ("unresolved", "not_found")
    assert not [n for n in doc["nodes"] if "FromOutside" in n["id"]]
    assert {f["path"]: f["flags"] for f in doc["coverage"]["files"]}["Bomb.slnx"] == ["parse_error"]
