"""Snapshot id without running git (research.md § R3, § R4)."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Mapping
from pathlib import Path

from graphora.ingest.walk import is_excluded_path

_GITLINK = 0o160000
_SYMLINK = 0o120000


def content_hash(contents: Mapping[str, bytes]) -> str:
    h = hashlib.sha256()
    for path in sorted(contents):
        h.update(path.encode("utf-8") + b"\0" + hashlib.sha256(contents[path]).hexdigest().encode() + b"\n")
    return h.hexdigest()[:16]


def _blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _under(rel: str, skipped: frozenset[str]) -> bool:
    parts = rel.split("/")
    return any("/".join(parts[: i + 1]) in skipped for i in range(len(parts)))


def _usable_git_dir(root: Path) -> bool:
    """Only a real .git directory whose data lives entirely inside the folder."""
    git = root / ".git"
    try:
        if not stat.S_ISDIR(os.lstat(git).st_mode):
            return False
    except OSError:
        return False
    return not (os.path.lexists(git / "objects" / "info" / "alternates") or os.path.lexists(git / "commondir"))


def _head_blobs(root: Path, skipped: frozenset[str]) -> tuple[str, dict[str, str]] | None:
    from dulwich.repo import Repo

    try:
        repo = Repo(str(root))
        try:
            head = repo.refs[b"HEAD"]
            tree = repo[repo[head].tree]
            blobs: dict[str, str] = {}
            stack = [("", tree)]
            while stack:
                prefix, current = stack.pop()
                for entry in current.iteritems():
                    rel = prefix + entry.path.decode("utf-8", errors="surrogateescape")
                    if entry.mode == _GITLINK or entry.mode == _SYMLINK:
                        continue
                    if stat.S_ISDIR(entry.mode):
                        stack.append((rel + "/", repo[entry.sha]))
                    elif not is_excluded_path(rel) and not _under(rel, skipped):
                        blobs[rel] = entry.sha.decode()
            return head.decode(), blobs
        finally:
            repo.close()
    except Exception:
        return None


def snapshot_id(root: Path, contents: Mapping[str, bytes], skipped_paths: tuple[str, ...] = ()) -> str:
    digest = content_hash(contents)
    if not _usable_git_dir(root):
        return f"content:{digest}"
    head = _head_blobs(root, frozenset(skipped_paths))
    if head is None:
        return f"content:{digest}"
    sha, head_blobs = head
    working = {path: _blob_id(data) for path, data in contents.items()}
    return sha if working == head_blobs else f"{sha}+dirty:{digest}"
