"""Git repositories built with dulwich for history tests, no git binary (specs/014-hotspots research § R11).

A commit spec is a dict: `files` (path -> bytes, or None to delete), `author` ("Name <mail>"), `time` (UTC
seconds), `parents` (indexes of earlier commits; default: the previous one; [] for a root)."""

from __future__ import annotations

import stat
from pathlib import Path

from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo

DAY = 86400
T0 = 1_750_000_000  # 2025-06-15T15:06:40Z


def _tree(repo: Repo, files: dict[str, bytes]) -> bytes:
    folders: dict[str, dict] = {}
    for path, data in files.items():
        node = folders
        *dirs, name = path.split("/")
        for d in dirs:
            node = node.setdefault(d, {})
        node[name] = data

    def write(node: dict) -> bytes:
        tree = Tree()
        for name, value in node.items():
            if isinstance(value, dict):
                tree.add(name.encode(), stat.S_IFDIR, write(value))
            else:
                blob = Blob.from_string(value)
                repo.object_store.add_object(blob)
                tree.add(name.encode(), 0o100644, blob.id)
        repo.object_store.add_object(tree)
        return tree.id

    return write(folders)


def make_repo(path: Path, commits: list[dict], checkout: bool = True) -> list[str]:
    """Writes the commits, points HEAD at the last one and, with `checkout`, writes its files to `path`."""
    path.mkdir(parents=True, exist_ok=True)
    repo = Repo.init(str(path))
    shas: list[bytes] = []
    states: list[dict[str, bytes]] = []
    try:
        for n, spec in enumerate(commits):
            parents = spec.get("parents", [n - 1] if n else [])
            files = dict(states[parents[0]]) if parents else {}
            for p, data in spec.get("files", {}).items():
                if data is None:
                    files.pop(p, None)
                else:
                    files[p] = data
            commit = Commit()
            commit.tree = _tree(repo, files)
            commit.parents = [shas[i] for i in parents]
            commit.author = commit.committer = spec.get("author", "Ann <ann@example.com>").encode()
            commit.author_time = commit.commit_time = spec.get("time", T0 + n * DAY)
            commit.author_timezone = commit.commit_timezone = 0
            commit.encoding = b"UTF-8"
            commit.message = spec.get("message", f"commit {n}").encode()
            repo.object_store.add_object(commit)
            shas.append(commit.id)
            states.append(files)
        repo.refs[b"refs/heads/master"] = shas[-1]
        repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/master")
    finally:
        repo.close()
    if checkout:
        for p, data in states[-1].items():
            target = path / p
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return [s.decode() for s in shas]


def make_shallow(path: Path, shas: list[str]) -> None:
    (path / ".git" / "shallow").write_text("".join(s + "\n" for s in sorted(shas)))
