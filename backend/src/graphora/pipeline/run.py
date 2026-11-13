"""The analyze-and-store flow shared by `graphora analyze --store` and the job runner
(specs/010-end-to-end-pipeline research § R2, contracts/pipeline-api.md)."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from graphora.graph.build import analyze
from graphora.ingest import github
from graphora.ingest.fetch import IngestLimits, fetch_snapshot, with_skipped
from graphora.ingest.source import GitHubSource, Source, ZipSource
from graphora.ingest.walk import Deadline

if TYPE_CHECKING:  # psycopg is imported only when a store is used
    from graphora.store import Store, StoredAnalysis

Stage = Literal["resolving", "fetching", "analyzing", "storing"]
Action = Literal["stored", "replaced", "reused"]

LIMIT_KEYS = ("max_files", "max_bytes", "max_seconds", "max_archive_bytes", "max_extract_bytes", "max_entries")


@dataclass(frozen=True)
class PipelineLimits:
    """The six ingest and analysis limits; defaults equal the `graphora analyze` defaults."""

    max_files: int = 5000
    max_bytes: int = 50 * 1024 * 1024
    max_seconds: float = 300
    max_archive_bytes: int = IngestLimits.max_archive_bytes
    max_extract_bytes: int = IngestLimits.max_extract_bytes
    max_entries: int = IngestLimits.max_entries

    def ingest(self) -> IngestLimits:
        return IngestLimits(self.max_archive_bytes, self.max_extract_bytes, self.max_entries)

    def as_dict(self) -> dict[str, float]:
        return {key: getattr(self, key) for key in LIMIT_KEYS}


@dataclass(frozen=True)
class PipelineResult:
    analysis: StoredAnalysis
    action: Action
    fetched: str | None  # the CLI's "fetched … at …" / "extracted …" info; None for a local folder or a reuse


def _no_stage(stage: Stage) -> None:
    pass


def run_pipeline(
    source: Source,
    limits: PipelineLimits,
    store: Store,
    deadline: Deadline,
    on_stage: Callable[[Stage], None] = _no_stage,
    workdir: Path | None = None,
) -> PipelineResult:
    """Resolve (GitHub), reuse or fetch, analyze and store. Raises the ingest, limit and store errors as is."""
    sha = None
    if isinstance(source, GitHubSource):
        on_stage("resolving")
        sha = github.resolve_sha(source, deadline)
        stored = store.find_reusable(f"github.com/{source.owner}/{source.repo}", sha)
        if stored is not None:  # nothing to download (005 FR-008)
            return PipelineResult(stored, "reused", None)
    on_stage("fetching")
    with fetch_snapshot(source, limits.ingest(), deadline, sha=sha, workdir=workdir) as fetched:
        on_stage("analyzing")
        result = analyze(fetched.root, limits.max_files, limits.max_bytes, deadline, snapshot=fetched.snapshot)
        result = dataclasses.replace(result, doc=with_skipped(result.doc, fetched.skipped))
        on_stage("storing")
        stored_result = store.put(fetched.repository, result)
    info = None
    if isinstance(source, GitHubSource):
        info = f"fetched {fetched.repository} at {fetched.snapshot}"
    elif isinstance(source, ZipSource):
        info = f"extracted {source.path.name}"
    return PipelineResult(stored_result.analysis, stored_result.action, info)
