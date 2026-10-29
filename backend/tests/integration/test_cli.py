import json

from conftest import FIXTURES, run_analyze

FLAT = FIXTURES / "py-flat" / "repo"


def _listing(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_missing_dir(tmp_path):
    code, out, err = run_analyze(tmp_path / "nope")
    assert code == 2 and out == b"" and "not a directory" in err


def test_path_is_file(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("import os\n")
    assert run_analyze(f)[0] == 2


def test_out_inside_analyzed_folder(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("import os\n")
    before = _listing(root)
    code, _, err = run_analyze(root, "--out", str(root / "graph.json"))
    assert code == 2 and "inside the analyzed folder" in err
    assert _listing(root) == before


def test_file_limit_writes_nothing(tmp_path):
    out = tmp_path / "graph.json"
    code, _, err = run_analyze(FLAT, "--max-files", "1", "--out", str(out))
    assert code == 3 and "file limit exceeded" in err
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


def test_time_limit_writes_nothing(tmp_path):
    out = tmp_path / "graph.json"
    code, _, err = run_analyze(FLAT, "--max-seconds", "0", "--out", str(out))
    assert code == 3 and "time limit exceeded" in err
    assert not out.exists()


def test_empty_folder(tmp_path, validator):
    root = tmp_path / "empty"
    root.mkdir()
    code, out, _ = run_analyze(root)
    assert code == 0
    doc = json.loads(out)
    validator.validate(doc)
    assert doc["nodes"] == [] and doc["edges"] == []


def test_stdout_when_no_out():
    code, out, err = run_analyze(FLAT)
    assert code == 0 and out.startswith(b"{") and out.endswith(b"}\n")
    assert err.startswith("graphora: info: analyzed 8 files")


def test_out_file(tmp_path):
    out = tmp_path / "graph.json"
    code, stdout, _ = run_analyze(FLAT, "--out", str(out))
    assert code == 0 and stdout == b""
    assert out.read_bytes() == run_analyze(FLAT)[1]


def test_unwritable_out(tmp_path):
    code, _, err = run_analyze(FLAT, "--out", str(tmp_path / "missing-dir" / "g.json"))
    assert code == 2 and "cannot write" in err


def test_broken_tsconfig_warns_and_succeeds(tmp_path):
    (tmp_path / "tsconfig.json").write_text('{ "compilerOptions": { oops } }\n')
    (tmp_path / "a.ts").write_text('import x from "./b";\n')
    code, out, err = run_analyze(tmp_path)
    assert code == 0, err
    assert "graphora: warning: ignoring tsconfig.json: not valid JSON-with-comments" in err
    assert err.index("warning") < err.index("info: analyzed")
    coverage = {f["path"]: f for f in json.loads(out)["coverage"]["files"]}
    assert coverage["tsconfig.json"]["flags"] == ["parse_error"]


def test_repeated_names_in_one_statement_give_one_edge(tmp_path):
    (tmp_path / "a.py").write_text("import os, os.path\nfrom m import f, f\n")
    (tmp_path / "m.py").write_text("def f(): pass\n")
    (tmp_path / "b.ts").write_text('import { a, a as b } from "./c";\n')
    (tmp_path / "c.ts").write_text("export const a = 1;\n")
    code, out, err = run_analyze(tmp_path)
    assert code == 0, err
    edges = json.loads(out)["edges"]
    assert [(e["source"], e["line"], e["target"], e["symbol"]) for e in edges] == [
        ("file:a.py", 1, "ext:python:os", None),
        ("file:a.py", 2, "file:m.py", "f"),
        ("file:b.ts", 1, "file:c.ts", "a"),
    ]
    assert len({e["id"] for e in edges}) == len(edges)


def test_broken_extends_target_flagged_in_coverage(tmp_path):
    (tmp_path / "tsconfig.json").write_text('{ "extends": "./tsconfig.base.json" }\n')
    (tmp_path / "tsconfig.base.json").write_text('{ "compilerOptions": { } oops\n')
    (tmp_path / "a.ts").write_text("export {};\n")
    code, out, err = run_analyze(tmp_path)
    assert code == 0 and "ignoring tsconfig.base.json" in err
    flags = {f["path"]: f["flags"] for f in json.loads(out)["coverage"]["files"]}
    assert flags["tsconfig.base.json"] == ["parse_error"]
    assert flags["tsconfig.json"] == []
