"""Git history of the snapshot commit, as counts per file (specs/014-hotspots)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dulwich.repo import Repo

    from graphora.graph.model import GraphDocument, History
    from graphora.ingest.fetch import FetchedSnapshot
    from graphora.ingest.source import Source
    from graphora.ingest.walk import Deadline

from graphora.ingest.fetch import IngestLimits

HISTORY_READER_VERSION = "1.0.0"


def collect_history(
    root: Path,
    doc: GraphDocument,
    *,
    deadline: Deadline,
    kind: str = "local",
    enabled: bool = True,
    source: Source | None = None,
    work: Path | None = None,
    max_bytes: int = IngestLimits.max_archive_bytes,
) -> History:
    from graphora.graph.model import FileNode, not_available
    from graphora.history.github import fetch_history
    from graphora.history.local import local_source
    from graphora.history.reader import read_history
    from graphora.ingest.source import GitHubSource

    if not enabled:
        return not_available("skipped")
    if kind == "zip":
        return not_available("zip")
    repo: Repo
    if kind == "github":
        assert isinstance(source, GitHubSource) and work is not None
        fetched = fetch_history(source, doc.snapshot, work / ".graphora-history", max_bytes, deadline)
        if isinstance(fetched, str):
            return not_available(fetched)
        repo, shallow = fetched
        sha, dirty = doc.snapshot, False
    else:
        found = local_source(root, doc.snapshot)
        if isinstance(found, str):
            return not_available(found)
        repo, sha, shallow, dirty = found
    paths = frozenset(n.path for n in doc.nodes if isinstance(n, FileNode))
    try:
        history = read_history(repo.object_store, sha, paths, shallow, deadline)
    except Exception:
        return not_available("unreadable")
    finally:
        repo.close()
    return dataclasses.replace(history, local_changes=dirty and history.status != "not_available")


def with_history(
    doc: GraphDocument, fetched: FetchedSnapshot, deadline: Deadline, enabled: bool = True, max_bytes: int = IngestLimits.max_archive_bytes
) -> GraphDocument:
    history = collect_history(
        fetched.root, doc, deadline=deadline, kind=fetched.kind, enabled=enabled, source=fetched.source,
        work=fetched.work, max_bytes=max_bytes,
    )
    return dataclasses.replace(doc, history=history)
