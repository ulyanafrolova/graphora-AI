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
    """007 SC-005: 1,000 C# files in 20 chained projects (transitive visibility, spread namespaces) in under 30 s."""
    import json

    for i in range(20):
        project = tmp_path / f"P{i}"
        project.mkdir()
        reference = f'<ItemGroup><ProjectReference Include="..\\P{i - 1}\\P{i - 1}.csproj" /></ItemGroup>' if i else ""
        (project / f"P{i}.csproj").write_text(f'<Project Sdk="Microsoft.NET.Sdk">{reference}</Project>\n')
        for m in range(50):
            usings = ["using System.Linq;", f"using P{i}.Area{(m + 1) % 5};"]
            if i:
                usings.append(f"using P{i - 1}.Area{m % 5};")
            body = f"namespace P{i}.Area{m % 5}\n{{\n    public class C{m}\n    {{\n        public int Run() => {m};\n    }}\n}}\n"
            (project / f"C{m}.cs").write_text("\n".join(usings) + "\n\n" + body)

    start = time.monotonic()
    code, out, err = run_analyze(tmp_path)
    elapsed = time.monotonic() - start

    assert code == 0, err
    # per file: 1 System.Linq + 10 files of a sibling namespace (+ 10 of the referenced project's namespace); 19 references
    assert "analyzed 1000 files, 20519 edges (0 unresolved)" in err
    assert elapsed < 30, f"took {elapsed:.1f}s"
    validator.validate(json.loads(out))
