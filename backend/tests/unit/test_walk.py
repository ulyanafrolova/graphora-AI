import os

import pytest

from graphora.ingest.walk import EXCLUDED_DIRS, Deadline, LimitExceeded, walk

BIG = 10**9


def _touch(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_sorted_posix_paths(tmp_path):
    for p in ["b.py", "a/z.py", "a/b/c.py", "a.py"]:
        _touch(tmp_path / p)
    assert walk(tmp_path, BIG, BIG).files == ["a.py", "a/b/c.py", "a/z.py", "b.py"]


@pytest.mark.parametrize("name", sorted(EXCLUDED_DIRS))
def test_excluded_dirs(tmp_path, name):
    _touch(tmp_path / name / "inner" / "x.py")
    _touch(tmp_path / "keep.py")
    result = walk(tmp_path, BIG, BIG)
    assert result.files == ["keep.py"]
    assert [(s.path, s.reason) for s in result.skipped] == [(name, "excluded_dir")]


def test_fr009_list_is_complete():
    assert EXCLUDED_DIRS == {
        ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
        "site-packages", "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
        # 003 FR-003
        ".next", ".nuxt", ".turbo", ".svelte-kit", "coverage", "out", "bower_components",
    }


def test_nested_repository(tmp_path):
    _touch(tmp_path / "vendor" / "lib" / ".git" / "HEAD")
    _touch(tmp_path / "vendor" / "lib" / "x.py")
    result = walk(tmp_path, BIG, BIG)
    assert result.files == []
    assert [(s.path, s.reason) for s in result.skipped] == [("vendor/lib", "nested_repository")]


def test_symlinks_not_followed(tmp_path):
    outside = tmp_path / "outside"
    _touch(outside / "secret.py")
    root = tmp_path / "root"
    _touch(root / "real.py")
    os.symlink(outside, root / "dirlink")
    os.symlink(root / "real.py", root / "filelink.py")
    result = walk(root, BIG, BIG)
    assert result.files == ["real.py"]
    assert [(s.path, s.reason) for s in result.skipped] == [("dirlink", "symlink"), ("filelink.py", "symlink")]


def test_minified(tmp_path):
    _touch(tmp_path / "static" / "app.min.js")
    _touch(tmp_path / "static" / "app.min.css")
    _touch(tmp_path / "static" / "app.js")
    result = walk(tmp_path, BIG, BIG)
    assert result.files == ["static/app.js"]
    assert {s.reason for s in result.skipped} == {"minified"}


def test_file_limit(tmp_path):
    for i in range(3):
        _touch(tmp_path / f"{i}.py")
    with pytest.raises(LimitExceeded) as exc:
        walk(tmp_path, 2, BIG)
    assert exc.value.limit == "files" and exc.value.value == 2


def test_byte_limit(tmp_path):
    _touch(tmp_path / "a.py", b"x" * 10)
    with pytest.raises(LimitExceeded) as exc:
        walk(tmp_path, BIG, 5)
    assert exc.value.limit == "bytes"


def test_skipped_do_not_count(tmp_path):
    _touch(tmp_path / ".venv" / "big.py", b"x" * 100)
    _touch(tmp_path / "a.py", b"x")
    assert walk(tmp_path, 1, 10).files == ["a.py"]


def test_deadline(tmp_path):
    _touch(tmp_path / "a.py")
    with pytest.raises(LimitExceeded) as exc:
        walk(tmp_path, BIG, BIG, Deadline(0))
    assert exc.value.limit == "seconds"
