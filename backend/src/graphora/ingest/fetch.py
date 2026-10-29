"""The fetch step: a source becomes a folder to analyze (specs/002-repo-ingest/contracts/ingest-api.md)."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from graphora.graph.model import GraphDocument, Skipped
from graphora.ingest.source import GitHubSource, LocalSource, Source, ZipSource
from graphora.ingest.walk import Deadline


@dataclass(frozen=True)
class IngestLimits:
    max_archive_bytes: int = 209715200
    max_extract_bytes: int = 209715200
    max_entries: int = 20000


@dataclass(frozen=True)
class FetchedSnapshot:
    root: Path
    repository: str
    snapshot: str | None  # None: build() computes it
    skipped: tuple[Skipped, ...]


def with_skipped(doc: GraphDocument, extra: tuple[Skipped, ...]) -> GraphDocument:
    if not extra:
        return doc
    return dataclasses.replace(doc, skipped=tuple(sorted(doc.skipped + extra, key=lambda s: s.path)))


@contextmanager
def fetch_snapshot(source: Source, limits: IngestLimits, deadline: Deadline) -> Iterator[FetchedSnapshot]:
    """Valid inside the `with` block; a temp folder is removed when the block exits."""
    if isinstance(source, LocalSource):
        root = source.path.resolve()
        yield FetchedSnapshot(root=root, repository=root.name, snapshot=None, skipped=())
    elif isinstance(source, GitHubSource):
        raise NotImplementedError("GitHub sources arrive in US1")
    elif isinstance(source, ZipSource):
        raise NotImplementedError("ZIP sources arrive in US2")
    else:
        raise TypeError(f"unknown source: {source!r}")