"""Git history of the snapshot commit, as counts per file (specs/014-hotspots)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from graphora.graph.model import GraphDocument, History
    from graphora.ingest.walk import Deadline

HISTORY_READER_VERSION = "1.0.0"


def collect_history(root: Path, doc: GraphDocument, *, deadline: Deadline, enabled: bool = True) -> History:
    from graphora.graph.model import FileNode, not_available
    from graphora.history.local import local_source
    from graphora.history.reader import read_history

    if not enabled:
        return not_available("skipped")
    source = local_source(root, doc.snapshot)
    if isinstance(source, str):
        return not_available(source)
    repo, sha, shallow, dirty = source
    paths = frozenset(n.path for n in doc.nodes if isinstance(n, FileNode))
    try:
        history = read_history(repo.object_store, sha, paths, shallow, deadline)
    except Exception:
        return not_available("unreadable")
    finally:
        repo.close()
    return dataclasses.replace(history, local_changes=dirty and history.status != "not_available")
