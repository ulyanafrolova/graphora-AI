"""SC-003: 10,000 commits over 5,000 files are read in at most 30 s (specs/014-hotspots)."""

import random
import time

import pytest
from dulwich.object_store import MemoryObjectStore
from dulwich.objects import Blob, Commit, Tree

from graphora.history.reader import read_history
from graphora.ingest.walk import Deadline

pytestmark = pytest.mark.slow

FOLDERS, PER_FOLDER, COMMITS = 50, 100, 10_000


def _history_store():
    """Commits touching 1-5 files each, all inside the window; only changed folders get new trees."""
    store = MemoryObjectStore()
    rng = random.Random(14)
    folders = {f"pkg{d}": {f"m{n}.py": b"" for n in range(PER_FOLDER)} for d in range(FOLDERS)}
    blobs: dict[bytes, bytes] = {}

    def blob(data: bytes) -> bytes:
        if data not in blobs:
            b = Blob.from_string(data)
            store.add_object(b)
            blobs[data] = b.id
        return blobs[data]

    def folder_tree(name: str) -> bytes:
        tree = Tree()
        for file, data in folders[name].items():
            tree.add(file.encode(), 0o100644, blob(data))
        store.add_object(tree)
        return tree.id

    trees = {name: folder_tree(name) for name in folders}
    parent = None
    for n in range(COMMITS):
        for _ in range(rng.randint(1, 5)):
            name = f"pkg{rng.randrange(FOLDERS)}"
            file = f"m{rng.randrange(PER_FOLDER)}.py"
            folders[name][file] = f"{n}".encode()
            trees[name] = folder_tree(name)
        root = Tree()
        for name, tree_id in trees.items():
            root.add(name.encode(), 0o040000, tree_id)
        store.add_object(root)
        commit = Commit()
        commit.tree, commit.parents = root.id, [parent] if parent else []
        commit.author = commit.committer = f"Dev{n % 7} <dev{n % 7}@example.com>".encode()
        commit.author_time = commit.commit_time = 1_750_000_000 + n * 60
        commit.author_timezone = commit.commit_timezone = 0
        commit.message = b"change"
        store.add_object(commit)
        parent = commit.id
    paths = frozenset(f"{name}/{file}" for name, files in folders.items() for file in files)
    return store, parent.decode(), paths


def test_ten_thousand_commits():
    store, head, paths = _history_store()
    begin = time.monotonic()
    history = read_history(store, head, paths, frozenset(), Deadline(600))
    elapsed = time.monotonic() - begin
    assert history.status == "available" and history.commits_read == COMMITS
    assert elapsed <= 30, f"{elapsed:.1f} s"
