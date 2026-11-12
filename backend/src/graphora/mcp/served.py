"""The one snapshot a server answers about, loaded once at start (specs/006-mcp-server research § R2, R10)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from graphora.graph import queries
from graphora.graph.load import loads

if TYPE_CHECKING:
    from graphora.store import Store


@dataclass(frozen=True)
class Served:
    index: queries.GraphIndex
    repository: str | None = None
    store: Store | None = None

    @property
    def snapshot(self) -> str:
        return self.index.doc.snapshot


class PairNotFound(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def from_graph_file(path: str | Path) -> Served:
    """Raises OSError for an unreadable file and InvalidGraph for a bad document."""
    return Served(queries.index(loads(Path(path).read_bytes())))


def from_store(url: str, repository: str, snapshot: str) -> Served:
    """A stored analysis (005). Raises StoreUnavailable, PairNotFound or InvalidGraph; the store is closed
    on failure and kept open in the returned value otherwise."""
    from graphora.store import Store

    store = Store.open(url)
    try:
        stored = store.get_analysis(repository, snapshot)
        if stored is None:
            if not store.has_repository(repository):
                raise PairNotFound(f"repository not found: {repository}")
            raise PairNotFound(f"snapshot not found: {repository} {snapshot}")
        return Served(queries.index(loads(stored.graph)), repository, store)
    except BaseException:
        store.close()
        raise
