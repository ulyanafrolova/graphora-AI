"""SC-005 (001 and 003): about 1,000 Python or TS files are analyzed in under 30 seconds."""

import time

import pytest

from conftest import run_analyze


@pytest.mark.slow
def test_thousand_files_under_30s(tmp_path):
    for p in range(10):
        pkg = tmp_path / f"pkg{p}"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        for m in range(100):
            imports = "\n".join(f"from pkg{(p + k) % 10} import mod{(m + k) % 100}" for k in (1, 2, 3))
            (pkg / f"mod{m}.py").write_text(f"{imports}\n\n\nclass C{m}:\n    def run(self):\n        return {m}\n")

    start = time.monotonic()
    code, out, err = run_analyze(tmp_path)
    elapsed = time.monotonic() - start

    assert code == 0, err
    assert "analyzed 1010 files, 3000 edges (0 unresolved)" in err
    assert elapsed < 30, f"took {elapsed:.1f}s"


@pytest.mark.slow
def test_thousand_ts_files_under_30s(tmp_path):
    """003 SC-005: about 1,000 TS files with relative and `paths` imports in under 30 seconds."""
    (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["*"]}}}\n')
    for p in range(10):
        pkg = tmp_path / f"pkg{p}"
        pkg.mkdir()
        for m in range(100):
            relative = "\n".join(f'import {{ C{(m + k) % 100} }} from "../pkg{(p + k) % 10}/mod{(m + k) % 100}";' for k in (1, 2, 3))
            alias = f'import {{ C{m} as Self }} from "@/pkg{(p + 4) % 10}/mod{m}";'
            (pkg / f"mod{m}.ts").write_text(f"{relative}\n{alias}\n\nexport class C{m} {{\n  run(): number {{\n    return {m};\n  }}\n}}\n")

    start = time.monotonic()
    code, out, err = run_analyze(tmp_path)
    elapsed = time.monotonic() - start

    assert code == 0, err
    assert "analyzed 1000 files, 4000 edges (0 unresolved)" in err
    assert elapsed < 30, f"took {elapsed:.1f}s"


@pytest.mark.slow
def test_thousand_csharp_files_in_20_projects_under_30s(tmp_path, validator):
    """007/008 SC-005: 1,000 C# files in 20 chained projects, with type references and implicit usings, in under 30 s."""
    import json

    (tmp_path / "Directory.Build.props").write_text("<Project><PropertyGroup><ImplicitUsings>enable</ImplicitUsings></PropertyGroup></Project>\n")
    for i in range(20):
        project = tmp_path / f"P{i}"
        project.mkdir()
        reference = f'<ItemGroup><ProjectReference Include="..\\P{i - 1}\\P{i - 1}.csproj" /></ItemGroup>' if i else ""
        (project / f"P{i}.csproj").write_text(f'<Project Sdk="Microsoft.NET.Sdk">{reference}</Project>\n')
        for m in range(50):
            usings = ["using System.Linq;", f"using P{i}.Area{(m + 1) % 5};"]
            if i:
                usings.append(f"using P{i - 1}.Area{m % 5};")
            nxt = f"C{(m + 1) % 50}"
            prev = f"        private P{i - 1}.Area{m % 5}.C{m} prev;\n" if i else ""
            body = (
                f"namespace P{i}.Area{m % 5}\n{{\n    public class C{m}\n    {{\n"
                f"        private {nxt} next = new {nxt}();\n{prev}"
                f"        public int Run() => {m};\n    }}\n}}\n"
            )
            (project / f"C{m}.cs").write_text("\n".join(usings) + "\n\n" + body)

    start = time.monotonic()
    code, out, err = run_analyze(tmp_path)
    elapsed = time.monotonic() - start

    assert code == 0, err
    # P0: per file 1 System.Linq + 1 type reference (its sibling-namespace using is used, so no fallback) = 100.
    # P1..P19: per file 1 + 1 + 10 fallback edges of the unused previous-project using + 1 qualified reference = 13,
    # 19 * 50 * 13 = 12,350; plus 19 project references.
    assert "analyzed 1000 files, 12469 edges (0 unresolved)" in err
    assert elapsed < 30, f"took {elapsed:.1f}s"
    validator.validate(json.loads(out))

    # 009 SC-005: project-level answers on the same graph in under 2 seconds in total
    from graphora.graph import queries
    from graphora.graph.load import loads

    ix = queries.index(loads(out))
    start = time.monotonic()
    impact = queries.impact(ix, "P0/P0.csproj", level="project")
    loops = queries.cycles(ix, level="project")
    summary = queries.projects(ix)
    elapsed = time.monotonic() - start
    assert [i.distance for i in impact.items] == list(range(1, 20))  # P1 … P19, one project further each
    assert loops.groups == () and summary.total == 20
    assert elapsed < 2, f"project level took {elapsed:.2f}s"
