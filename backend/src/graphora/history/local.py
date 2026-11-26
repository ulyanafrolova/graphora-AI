"""The git history of a local folder, read as data with dulwich (specs/014-hotspots research § R2)."""

from __future__ import annotations

from pathlib import Path

from dulwich.repo import Repo

from graphora.graph.model import HistoryReason
from graphora.ingest.snapshot import _usable_git_dir


def local_source(root: Path, snapshot: str) -> tuple[Repo, str, frozenset[bytes], bool] | HistoryReason:
    """The repository, the snapshot commit, the shallow commits and whether the tree is dirty; or why not."""
    if snapshot.startswith("content:") or not _usable_git_dir(root):
        return "no_git"
    sha, _, dirty = snapshot.partition("+dirty:")
    try:
        repo = Repo(str(root))
    except Exception:
        return "unreadable"
    try:
        return repo, sha, frozenset(repo.get_shallow()), bool(dirty)
    except Exception:
        repo.close()
        return "unreadable"
