"""Files and folders without read permission (001 spec edge case "Files that cannot be decoded": `unreadable`)."""

import json
import os
from contextlib import contextmanager

import pytest

from conftest import run_analyze

pytestmark = pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads everything")


@contextmanager
def _no_permission(path):
    mode = path.stat().st_mode
    path.chmod(0)
    try:
        yield
    finally:
        path.chmod(mode)  # so pytest can remove tmp_path


def test_unreadable_files_are_flagged_not_fatal(tmp_path):
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("import os\n")
    (tmp_path / "c.ts").write_text('import "./a";\n')
    (tmp_path / "notes.txt").write_text("x\n")
    (tmp_path / "tsconfig.json").write_text("{}\n")
    with _no_permission(tmp_path / "b.py"), _no_permission(tmp_path / "c.ts"), _no_permission(tmp_path / "notes.txt"), _no_permission(tmp_path / "tsconfig.json"):
        code, out, err = run_analyze(tmp_path)

    assert code == 0, err
    doc = json.loads(out)
    flags = {f["path"]: f["flags"] for f in doc["coverage"]["files"]}
    assert flags == {
        "a.py": [],
        "b.py": ["unreadable"],
        "c.ts": ["unreadable"],
        "notes.txt": ["unreadable"],
        "tsconfig.json": ["parse_error", "unreadable"],
    }
    assert {n["id"] for n in doc["nodes"] if n["kind"] == "file"} == {"file:a.py", "file:b.py", "file:c.ts"}
    assert [(e["source"], e["target"]) for e in doc["edges"]] == [("file:a.py", "file:b.py")]


def test_unreadable_folder_is_a_clear_error(tmp_path):
    (tmp_path / "locked").mkdir()
    (tmp_path / "locked" / "x.py").write_text("")
    out_file = tmp_path.parent / f"{tmp_path.name}-graph.json"
    with _no_permission(tmp_path / "locked"):
        code, out, err = run_analyze(tmp_path, "--out", str(out_file))

    assert code == 2 and "cannot read folder locked" in err and "Traceback" not in err
    assert not out_file.exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs FIFOs")
def test_special_files_listed_never_opened(tmp_path):
    """001 FR-007: every file is accounted for. Opening a FIFO would block the run forever."""
    (tmp_path / "a.py").write_text("import pipe\n")
    os.mkfifo(tmp_path / "pipe.py")
    os.mkfifo(tmp_path / "data")
    code, out, err = run_analyze(tmp_path)

    assert code == 0, err
    doc = json.loads(out)
    assert {f["path"]: f["flags"] for f in doc["coverage"]["files"]} == {"a.py": [], "data": ["unreadable"], "pipe.py": ["unreadable"]}
    assert [(e["source"], e["target"]) for e in doc["edges"]] == [("file:a.py", "file:pipe.py")]
