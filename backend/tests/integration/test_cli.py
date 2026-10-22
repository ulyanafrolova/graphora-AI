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
