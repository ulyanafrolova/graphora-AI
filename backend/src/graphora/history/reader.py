"""Commits and authors per file in the year before the snapshot commit (specs/014-hotspots research § R3, R4, R7)."""

from __future__ import annotations

import heapq
from collections import defaultdict
from datetime import UTC, datetime

from dulwich.diff_tree import CHANGE_ADD, CHANGE_MODIFY, tree_changes
from dulwich.object_store import BaseObjectStore

from graphora.graph.model import FileHistory, History, not_available
from graphora.ingest.walk import Deadline

WINDOW_SECONDS = 365 * 86400


def utc(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _identity(author: bytes) -> bytes:
    start, end = author.rfind(b"<"), author.rfind(b">")
    return (author[start + 1 : end] if 0 <= start < end else author).strip().lower()


def read_history(
    store: BaseObjectStore, commit_sha: str, paths: frozenset[str], shallow: frozenset[bytes], deadline: Deadline
) -> History:
    head = store[commit_sha.encode()]
    window_start = head.commit_time - WINDOW_SECONDS
    commits: dict[str, int] = defaultdict(int)
    authors: dict[str, set[bytes]] = defaultdict(set)
    read = merges = cut = 0
    newest = oldest = None
    partial = False

    queue = [(-head.commit_time, head.id)]
    seen = {head.id}
    while queue:
        if deadline.remaining() <= 0:
            partial = True
            break
        _, sha = heapq.heappop(queue)
        commit = store[sha]
        if commit.commit_time < window_start:
            continue
        if sha in shallow:
            cut += 1
            continue
        for parent in commit.parents:
            if parent not in seen:
                seen.add(parent)
                heapq.heappush(queue, (-store[parent].commit_time, parent))
        if len(commit.parents) > 1:
            merges += 1
            continue
        parent_tree = store[commit.parents[0]].tree if commit.parents else None
        who = _identity(commit.author)
        for change in tree_changes(store, parent_tree, commit.tree):
            if change.type not in (CHANGE_ADD, CHANGE_MODIFY):
                continue
            path = change.new.path.decode("utf-8", "surrogateescape")
            if path in paths:
                commits[path] += 1
                authors[path].add(who)
        read += 1
        newest = commit.commit_time if newest is None else max(newest, commit.commit_time)
        oldest = commit.commit_time if oldest is None else min(oldest, commit.commit_time)

    if partial and read == 0:
        return not_available("time_limit")
    return History(
        "partial" if partial else "available",
        None,
        commit_sha,
        utc(window_start),
        None if newest is None else utc(newest),
        None if oldest is None else utc(oldest),
        read,
        merges,
        cut,
        False,
        tuple(FileHistory(p, commits[p], len(authors[p])) for p in sorted(commits)),
    )
