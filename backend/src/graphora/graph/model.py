"""In-memory graph model. Field meanings are defined in specs/001-python-graph-cli/data-model.md."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

Confidence = Literal["resolved", "heuristic", "unresolved"]
Reason = Literal["not_found", "relative_beyond_top", "namespace_package", "dynamic"]
Status = Literal["analyzed", "detected_only", "not_code"]
Flag = Literal["parse_error", "unreadable"]
SkipReason = Literal["excluded_dir", "nested_repository", "symlink", "minified"]
DefinitionKind = Literal["class", "function", "method"]
Category = Literal["stdlib", "third_party"]


@dataclass(frozen=True)
class Definition:
    kind: DefinitionKind
    name: str
    line: int


@dataclass(frozen=True)
class FileNode:
    path: str
    definitions: tuple[Definition, ...] = ()

    @property
    def id(self) -> str:
        return f"file:{self.path}"


@dataclass(frozen=True)
class ExternalNode:
    name: str
    category: Category

    @property
    def id(self) -> str:
        return f"ext:{self.name}"


@dataclass(frozen=True)
class UnresolvedNode:
    reference: str

    @property
    def id(self) -> str:
        return f"unresolved:{self.reference}"


Node = Union[FileNode, ExternalNode, UnresolvedNode]


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    symbol: str | None
    line: int
    column: int
    snapshot: str
    confidence: Confidence
    reason: Reason | None
    extractor: str
    snippet_hash: str

    def __post_init__(self) -> None:
        if (self.confidence == "unresolved") != (self.reason is not None):
            raise ValueError("reason is required exactly when confidence is 'unresolved'")


@dataclass(frozen=True)
class CoverageFile:
    path: str
    language: str | None
    status: Status
    flags: tuple[Flag, ...] = ()


@dataclass(frozen=True)
class Skipped:
    path: str
    reason: SkipReason


@dataclass(frozen=True)
class GraphDocument:
    snapshot: str
    extractors: dict[str, str]
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    files: tuple[CoverageFile, ...]
    skipped: tuple[Skipped, ...]
