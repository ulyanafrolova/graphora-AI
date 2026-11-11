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


def from_graph_file(path: str | Path) -> Served:
    """Raises OSError for an unreadable file and InvalidGraph for a bad document."""
    return Served(queries.index(loads(Path(path).read_bytes())))
