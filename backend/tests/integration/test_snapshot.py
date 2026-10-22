"""Snapshot ids for git working trees, built with dulwich so the git binary is not needed."""

import json
import os
import re

from dulwich import porcelain

from conftest import run_analyze

SHA = r"[0-9a-f]{40}"
HEX16 = r"[0-9a-f]{16}"


def _snapshot(root):
    code, out, err = run_analyze(root)
    assert code == 0, err
    return json.loads(out)["snapshot"]


def _repo(path, files):
    path.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text)
    repo = porcelain.init(str(path))
    porcelain.add(repo, [str(path / name) for name in files])
    sha = porcelain.commit(repo, message=b"init", author=b"T <t@example.com>", committer=b"T <t@example.com>")
    repo.close()
    return sha.decode()


def test_clean_tree_gives_head_sha(tmp_path):
    root = tmp_path / "r"
    sha = _repo(root, {"a.py": "import os\n", "pkg/__init__.py": ""})
    assert _snapshot(root) == sha


def test_modified_file_gives_dirty(tmp_path):
    root = tmp_path / "r"
    sha = _repo(root, {"a.py": "import os\n"})
    (root / "a.py").write_text("import sys\n")
    first = _snapshot(root)
    assert re.fullmatch(rf"{sha}\+dirty:{HEX16}", first)
    assert _snapshot(root) == first


def test_untracked_file_gives_dirty(tmp_path):
    root = tmp_path / "r"
    sha = _repo(root, {"a.py": "import os\n"})
    (root / "new.py").write_text("import json\n")
    assert _snapshot(root).startswith(f"{sha}+dirty:")


def test_change_inside_skipped_dir_stays_clean(tmp_path):
    root = tmp_path / "r"
    sha = _repo(root, {"a.py": "import os\n", ".venv/lib/x.py": "x = 1\n"})
    (root / ".venv" / "lib" / "x.py").write_text("x = 2\n")
    (root / ".venv" / "new.py").write_text("y = 1\n")
    assert _snapshot(root) == sha


def test_git_file_gives_content(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.py").write_text("import os\n")
    (root / ".git").write_text("gitdir: ../elsewhere\n")
    assert re.fullmatch(rf"content:{HEX16}", _snapshot(root))


def test_unborn_head_gives_content(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.py").write_text("import os\n")
    porcelain.init(str(root)).close()
    assert re.fullmatch(rf"content:{HEX16}", _snapshot(root))


def test_symlinked_git_dir_gives_content(tmp_path):
    outside = tmp_path / "outside"
    _repo(outside, {"a.py": "import os\n"})
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.py").write_text("import os\n")
    os.symlink(outside / ".git", root / ".git")
    assert re.fullmatch(rf"content:{HEX16}", _snapshot(root))


def test_alternates_gives_content(tmp_path):
    root = tmp_path / "r"
    _repo(root, {"a.py": "import os\n"})
    (root / ".git" / "objects" / "info").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "objects" / "info" / "alternates").write_text(str(tmp_path / "other" / "objects") + "\n")
    assert re.fullmatch(rf"content:{HEX16}", _snapshot(root))


def test_commondir_gives_content(tmp_path):
    root = tmp_path / "r"
    _repo(root, {"a.py": "import os\n"})
    (root / ".git" / "commondir").write_text("../../elsewhere\n")
    assert re.fullmatch(rf"content:{HEX16}", _snapshot(root))


def test_content_id_matches_for_non_git_copy(tmp_path):
    root = tmp_path / "r"
    _repo(root, {"a.py": "import os\n"})
    (root / "a.py").write_text("import sys\n")
    dirty = _snapshot(root)
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "a.py").write_text("import sys\n")
    assert dirty.split("+dirty:")[1] == _snapshot(plain).split("content:")[1]
