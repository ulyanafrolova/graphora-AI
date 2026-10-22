"""Constitution Principle I: analysis never executes analyzed code or git-configured commands."""

import shutil

from dulwich import porcelain

from conftest import FIXTURES, run_analyze


def _tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_no_code_or_git_hooks_run(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "py-dynamic" / "repo", root, symlinks=True)
    repo = porcelain.init(str(root))
    porcelain.add(repo, [str(root / "loader.py"), str(root / "plugins" / "evil.py")])
    porcelain.commit(repo, message=b"init", author=b"T <t@example.com>", committer=b"T <t@example.com>")
    repo.close()

    filter_marker = tmp_path / "GIT_FILTER_MARKER"
    fsmonitor_marker = tmp_path / "FSMONITOR_MARKER"
    (root / ".gitattributes").write_text("* filter=evil\n")
    with open(root / ".git" / "config", "a") as config:
        config.write(f'[filter "evil"]\n\tclean = touch {filter_marker}\n\tsmudge = touch {filter_marker}\n')
        config.write(f"[core]\n\tfsmonitor = touch {fsmonitor_marker}\n")
    before = _tree(root)

    code, out, err = run_analyze(root)

    assert code == 0, err
    assert not (root / "plugins" / "IMPORTED_MARKER").exists()
    assert not filter_marker.exists()
    assert not fsmonitor_marker.exists()
    assert _tree(root) == before
