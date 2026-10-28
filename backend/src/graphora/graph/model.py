"""In-memory graph model. Field meanings are defined in specs/001-python-graph-cli/data-model.md and the v2
changes in specs/003-ts-js-analysis/data-model.md."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

Confidence = Literal["resolved", "heuristic", "unresolved"]
Reason = Literal["not_found", "relative_beyond_top", "namespace_package", "dynamic", "workspace_package"]
Status = Literal["analyzed", "detected_only", "not_code"]
Flag = Literal["parse_error", "unreadable"]
SkipReason = Literal["excluded_dir", "nested_repository", "symlink", "minified"]
DefinitionKind = Literal["class", "function", "method", "interface", "type_alias", "enum"]
Category = Literal["stdlib", "builtin", "third_party"]
Ecosystem = Literal["python", "npm"]
Form = Literal["static", "dynamic", "require"]
EdgeType = Literal["imports", "reexports"]


@dataclass(frozen=True)
class Definition:
    kind: DefinitionKind
    name: str
    line: int
    exported_as: tuple[str, ...] | None = None  # None for Python; names it is exported under for TS/JS


@dataclass(frozen=True)
class Export:
    """An exported TS/JS name that is not backed by a definition in the same file."""

    name: str
    local: str | None
    line: int


@dataclass(frozen=True)
class FileNode:
    path: str
    language: str
    definitions: tuple[Definition, ...] = ()
    exports: tuple[Export, ...] | None = None  # None for Python

    @property
    def id(self) -> str:
        return f"file:{self.path}"


@dataclass(frozen=True)
class ExternalNode:
    name: str
    ecosystem: Ecosystem
    category: Category

    @property
    def id(self) -> str:
        return f"ext:{self.ecosystem}:{self.name}"


@dataclass(frozen=True)
class UnresolvedNode:
    reference: str
    ecosystem: Ecosystem

    @property
    def id(self) -> str:
        return f"unresolved:{self.ecosystem}:{self.reference}"


@dataclass(frozen=True)
class AssetNode:
    path: str

    @property
    def id(self) -> str:
        return f"asset:{self.path}"


Node = Union[FileNode, ExternalNode, UnresolvedNode, AssetNode]


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
    type: EdgeType = "imports"
    form: Form = "static"
    type_only: bool = False
    alias: str | None = None

    def __post_init__(self) -> None:
        if (self.confidence == "unresolved") != (self.reason is not None):
            raise ValueError("reason is required exactly when confidence is 'unresolved'")
        if self.alias is not None and self.type != "reexports":
            raise ValueError("alias is allowed only on 'reexports' edges")
        if self.type == "reexports" and self.form != "static":
            raise ValueError("'reexports' edges always have form 'static'")


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
