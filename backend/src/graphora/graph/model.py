"""In-memory graph model. Field meanings are defined in specs/001-python-graph-cli/data-model.md and the v2
changes in specs/003-ts-js-analysis/data-model.md. v3 adds the `unreadable_dir` skip reason (issue #10). v4 adds C#
(specs/007-csharp-analysis/data-model.md), v5 C# type references (specs/008-csharp-type-references/data-model.md)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union, get_args

Confidence = Literal["resolved", "heuristic", "unresolved"]
UnresolvedReason = Literal[
    "not_found",
    "relative_beyond_top",
    "namespace_package",
    "dynamic",
    "workspace_package",
    "not_referenced",
    "no_types",
    "ambiguous",
    "msbuild_property",
    "not_csharp",
]
HeuristicReason = Literal["namespace_spread", "partial_type", "package_prefix", "msbuild_condition"]
Reason = Literal[UnresolvedReason, HeuristicReason]
Status = Literal["analyzed", "detected_only", "not_code"]
Flag = Literal["parse_error", "unreadable", "ambiguous_project"]
SkipReason = Literal["excluded_dir", "nested_repository", "symlink", "minified", "unreadable_dir"]
DefinitionKind = Literal["class", "function", "method", "interface", "type_alias", "enum", "struct", "record", "delegate"]
Category = Literal["stdlib", "builtin", "third_party"]
Ecosystem = Literal["python", "npm", "dotnet", "nuget"]
Form = Literal["static", "dynamic", "require"]
EdgeType = Literal["imports", "reexports", "project_reference", "package_reference", "type_reference", "solution_member"]
Directive = Literal["using", "using_static", "using_alias"]

UNRESOLVED_REASONS: frozenset[str] = frozenset(get_args(UnresolvedReason))
HEURISTIC_REASONS: frozenset[str] = frozenset(get_args(HeuristicReason))


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
    exports: tuple[Export, ...] | None = None  # None for Python and C#
    project: str | None = None  # C# only: `project:<path>` of the owning .csproj, or None

    @property
    def id(self) -> str:
        return f"file:{self.path}"


@dataclass(frozen=True)
class ProjectNode:
    """A `.csproj` file."""

    path: str

    @property
    def id(self) -> str:
        return f"project:{self.path}"


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


@dataclass(frozen=True)
class SolutionNode:
    """A `.sln` or `.slnx` file (specs/009-csharp-solutions-project-views)."""

    path: str

    @property
    def id(self) -> str:
        return f"solution:{self.path}"


Node = Union[FileNode, ExternalNode, UnresolvedNode, AssetNode, ProjectNode, SolutionNode]


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
    directive: Directive | None = None  # C# `using` edges only
    global_using: bool | None = None  # set exactly when `directive` is

    def __post_init__(self) -> None:
        if self.confidence == "resolved" and self.reason is not None:
            raise ValueError("a 'resolved' edge has no reason")
        if self.confidence == "unresolved" and self.reason not in UNRESOLVED_REASONS:
            raise ValueError("an 'unresolved' edge needs an unresolved reason")
        if self.confidence == "heuristic" and self.reason not in HEURISTIC_REASONS:
            raise ValueError("a 'heuristic' edge needs a heuristic reason")
        if (self.directive is None) != (self.global_using is None):
            raise ValueError("directive and global_using are set together")
        if self.directive is not None and self.type != "imports":
            raise ValueError("directive is allowed only on 'imports' edges")
        if self.alias is not None and self.type != "reexports" and self.directive != "using_alias":
            raise ValueError("alias is allowed only on 'reexports' and 'using_alias' edges")
        if self.directive == "using_alias" and self.alias is None:
            raise ValueError("a 'using_alias' edge needs an alias")
        if self.type == "type_reference" and (self.directive is not None or self.alias is not None):
            raise ValueError("a 'type_reference' edge has no directive and no alias")
        if self.type == "reexports" and self.form != "static":
            raise ValueError("'reexports' edges always have form 'static'")


@dataclass(frozen=True)
class CoverageFile:
    path: str
    language: str | None
    status: Status
    flags: tuple[Flag, ...] = ()
    unresolved_type_names: int | None = None  # 008: analyzed C# files only


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
