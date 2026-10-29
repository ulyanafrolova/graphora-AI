"""What the user asked to analyze (specs/002-repo-ingest/research.md § R4, data-model.md § Source)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from graphora.ingest.errors import BadInput


@dataclass(frozen=True)
class LocalSource:
    path: Path


@dataclass(frozen=True)
class GitHubSource:
    owner: str
    repo: str
    ref: str | None


@dataclass(frozen=True)
class ZipSource:
    path: Path


Source = LocalSource | GitHubSource | ZipSource


def parse_source(argument: str, ref: str | None) -> Source:
    path = Path(argument)
    if path.is_dir():
        if ref is not None:
            raise BadInput("--ref is allowed only with a GitHub link")
        return LocalSource(path)
    raise BadInput(f"not a directory or ZIP archive: {argument}")
