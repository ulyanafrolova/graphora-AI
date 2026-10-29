"""The fetch step: a source becomes a folder to analyze (specs/002-repo-ingest/contracts/ingest-api.md)."""

from __future__ import annotations

import dataclasses
import os
import tempfile
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from graphora.graph.model import GraphDocument, Skipped
from graphora.ingest import github
from graphora.ingest.archive import extract_tar_gz, extract_zip
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
        sha = github.resolve_sha(source, deadline)
        with tempfile.TemporaryDirectory(prefix="graphora-") as tmp:
            with closing(github.open_tarball(source, sha, limits, deadline)) as stream:
                root, skipped = extract_tar_gz(stream, Path(tmp), limits, deadline, expected_sha=sha)
            if not os.path.lexists(root / ".git"):
                os.mkdir(root / ".git", 0o755)  # a clone has one: the walk reports it the same way (FR-016)
            yield FetchedSnapshot(root, f"github.com/{source.owner}/{source.repo}", sha, skipped)
    elif isinstance(source, ZipSource):
        name = source.path.name
        with tempfile.TemporaryDirectory(prefix="graphora-") as tmp:
            root, skipped = extract_zip(source.path, Path(tmp), limits, deadline)
            yield FetchedSnapshot(root, name.rsplit(".", 1)[0] if "." in name else name, None, skipped)
    else:
        raise TypeError(f"unknown source: {source!r}")
