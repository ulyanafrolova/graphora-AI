"""Fetched sources give the same graph as the folder (specs/002-repo-ingest FR-016, SC-002; research.md § R9, R10)."""

import json
import re
import shutil

import pytest
from dulwich import porcelain

from archives import tar_of_dir, zip_of_dir
from conftest import FIXTURES, run_analyze
from fake_github import FakeGitHub
from graphora.ingest import github

FIXTURE_NAMES = sorted(p.name for p in FIXTURES.iterdir() if (p / "repo").is_dir())


def _clone(name, tmp_path):
    clone = tmp_path / "clone"
    shutil.copytree(FIXTURES / name / "repo", clone, symlinks=True)
    repo = porcelain.init(str(clone))
    paths = sorted(str(p) for p in clone.rglob("*") if (p.is_file() or p.is_symlink()) and ".git" not in p.parts)
    porcelain.add(repo, paths)
    sha = porcelain.commit(repo, message=b"fixture", author=b"T <t@example.com>", committer=b"T <t@example.com>")
    repo.close()
    return clone, sha.decode()


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_link_equals_clone(name, tmp_path, monkeypatch):
    clone, sha = _clone(name, tmp_path)
    fake = FakeGitHub()
    fake.serve("https://api.github.com/repos/o/r/commits/HEAD", body=sha.encode())
    fake.serve(
        f"https://codeload.github.com/o/r/tar.gz/{sha}",
        body=tar_of_dir(clone, f"o-r-{sha[:7]}", pax_comment=sha, exclude={".git"}),
    )
    monkeypatch.setattr(github, "_open", fake)

    local = run_analyze(clone)
    first = run_analyze("https://github.com/o/r")
    second = run_analyze("https://github.com/o/r")
    assert local[0] == first[0] == 0, first[2]
    assert f'"snapshot": "{sha}"'.encode() in local[1]
    assert first[1] == local[1]
    assert second[1] == first[1]


def _snapshot(out):
    return json.loads(out)["snapshot"]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
@pytest.mark.parametrize("prefix", ["proj", None])
def test_zip_equals_folder(name, prefix, tmp_path):
    folder = FIXTURES / name / "repo"
    archive = tmp_path / "proj.zip"
    archive.write_bytes(zip_of_dir(folder, prefix=prefix))

    local = run_analyze(folder)
    first = run_analyze(archive)
    second = run_analyze(archive)
    assert local[0] == first[0] == 0, first[2]
    assert re.fullmatch(r"content:[0-9a-f]{16}", _snapshot(first[1]))
    expected = local[1].replace(_snapshot(local[1]).encode(), _snapshot(first[1]).encode())
    assert first[1] == expected
    assert second[1] == first[1]


def test_zip_with_git_folder_keeps_content_snapshot(tmp_path):
    folder = tmp_path / "proj"
    shutil.copytree(FIXTURES / "py-flat" / "repo", folder)
    (folder / ".git").mkdir()
    (folder / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (folder / ".git" / "config").write_text("[core]\n")
    archive = tmp_path / "proj.zip"
    archive.write_bytes(zip_of_dir(folder))

    code, out, err = run_analyze(archive)
    assert code == 0, err
    assert _snapshot(out).startswith("content:")
