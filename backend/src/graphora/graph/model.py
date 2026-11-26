"""In-memory graph model. Field meanings are defined in specs/001-python-graph-cli/data-model.md and the v2
changes in specs/003-ts-js-analysis/data-model.md. v3 adds the `unreadable_dir` skip reason (issue #10). v4 adds C#
(specs/007-csharp-analysis/data-model.md), v5 C# type references (specs/008-csharp-type-references/data-model.md).
v8 adds history (specs/014-hotspots/data-model.md)."""

from __future__ import annotations

import re
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
HeuristicReason = Literal["namespace_spread", "partial_type", "package_prefix", "msbuild_condition", "http_route"]
Reason = Literal[UnresolvedReason, HeuristicReason]
Status = Literal["analyzed", "detected_only", "not_code"]
Flag = Literal["parse_error", "unreadable", "ambiguous_project"]
SkipReason = Literal["excluded_dir", "nested_repository", "symlink", "minified", "unreadable_dir"]
DefinitionKind = Literal["class", "function", "method", "interface", "type_alias", "enum", "struct", "record", "delegate"]
Category = Literal["stdlib", "builtin", "third_party"]
Ecosystem = Literal["python", "npm", "dotnet", "nuget", "http"]
Form = Literal["static", "dynamic", "require"]
EdgeType = Literal[
    "imports", "reexports", "project_reference", "package_reference", "type_reference", "solution_member", "http_call"
]
Directive = Literal["using", "using_static", "using_alias"]
HistoryStatus = Literal["available", "partial", "not_available"]
HistoryReason = Literal["no_git", "zip", "unreadable", "skipped", "fetch_failed", "too_large", "time_limit", "not_collected"]

UNRESOLVED_REASONS: frozenset[str] = frozenset(get_args(UnresolvedReason))
HEURISTIC_REASONS: frozenset[str] = frozenset(get_args(HeuristicReason))
FINAL_HISTORY_REASONS = frozenset({"no_git", "zip", "unreadable"})
_SHA = re.compile(r"[0-9a-f]{40}")


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
    route_line: int | None = None  # 015: the route's line in the target file, `http_call` edges to a file only

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
        python_import = self.type == "imports" and self.extractor.startswith("python-adapter@")
        if self.alias is not None and self.type != "reexports" and self.directive != "using_alias" and not python_import:
            raise ValueError("alias is allowed only on 'reexports', 'using_alias' and Python 'imports' edges")
        if python_import and self.alias is not None and self.alias == self.symbol:
            raise ValueError("a Python import alias differs from its symbol")
        if self.directive == "using_alias" and self.alias is None:
            raise ValueError("a 'using_alias' edge needs an alias")
        if self.type == "type_reference" and (self.directive is not None or self.alias is not None):
            raise ValueError("a 'type_reference' edge has no directive and no alias")
        if self.type == "reexports" and self.form != "static":
            raise ValueError("'reexports' edges always have form 'static'")
        if self.type == "http_call":  # the same rules as schema v8 (specs/015-http-bridge contracts)
            if self.confidence == "resolved":
                raise ValueError("an 'http_call' edge is never 'resolved'")
            if not self.source.startswith("file:") or self.form != "static" or self.type_only:
                raise ValueError("an 'http_call' edge goes from a file, static and not type-only")
            if self.confidence == "heuristic" and (self.reason != "http_route" or not self.target.startswith("file:")):
                raise ValueError("a heuristic 'http_call' edge has reason 'http_route' and a file target")
            if self.confidence == "unresolved" and (
                self.reason not in ("dynamic", "not_found", "ambiguous") or not self.target.startswith("unresolved:http:")
            ):
                raise ValueError("an unresolved 'http_call' edge has reason dynamic, not_found or ambiguous and an http target")
            if (self.route_line is not None) != self.target.startswith("file:"):
                raise ValueError("route_line is set exactly on 'http_call' edges to a file")
            if self.route_line is not None and self.route_line < 1:
                raise ValueError("route_line is at least 1")
        elif self.route_line is not None:
            raise ValueError("route_line is allowed only on 'http_call' edges")
        elif self.reason == "http_route":
            raise ValueError("reason 'http_route' is allowed only on 'http_call' edges")


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
class FileHistory:
    path: str
    commits: int
    authors: int  # bus factor


@dataclass(frozen=True)
class History:
    """Counts from the git history of the snapshot commit; no names or e-mail addresses."""

    status: HistoryStatus
    reason: HistoryReason | None
    commit: str | None
    window_start: str | None
    newest: str | None
    oldest: str | None
    commits_read: int
    merges_skipped: int
    shallow_skipped: int
    local_changes: bool
    files: tuple[FileHistory, ...]

    def __post_init__(self) -> None:
        if self.status not in get_args(HistoryStatus):
            raise ValueError(f"unknown history status: {self.status!r}")
        if min(self.commits_read, self.merges_skipped, self.shallow_skipped) < 0:
            raise ValueError("history counts are 0 or more")
        if self.status == "not_available":
            if self.reason not in get_args(HistoryReason):
                raise ValueError("history 'not_available' needs a reason")
            if (
                any(v is not None for v in (self.commit, self.window_start, self.newest, self.oldest))
                or self.commits_read or self.merges_skipped or self.shallow_skipped or self.local_changes or self.files
            ):
                raise ValueError("history 'not_available' has no commit, dates, counts or files")
            return
        if self.reason is not None:
            raise ValueError(f"history '{self.status}' has no reason")
        if self.commit is None or not _SHA.fullmatch(self.commit) or self.window_start is None:
            raise ValueError(f"history '{self.status}' needs a commit and a window start")
        if (self.newest is None or self.oldest is None) != (self.commits_read == 0):
            raise ValueError("newest and oldest are set exactly when commits were read")
        if self.status == "partial" and self.commits_read == 0:
            raise ValueError("a partial history has read at least one commit")
        paths = [f.path for f in self.files]
        if paths != sorted(set(paths)):
            raise ValueError("history files are unique and sorted by path")
        for f in self.files:
            if not 1 <= f.authors <= f.commits:
                raise ValueError(f"history of {f.path}: 1 <= authors <= commits")

    @property
    def final(self) -> bool:
        """Retrying the analysis cannot give a better history (research § R6)."""
        return self.status == "available" or (self.status == "not_available" and self.reason in FINAL_HISTORY_REASONS)


def not_available(reason: HistoryReason) -> History:
    return History("not_available", reason, None, None, None, None, 0, 0, 0, False, ())


NOT_COLLECTED = not_available("not_collected")


@dataclass(frozen=True)
class GraphDocument:
    snapshot: str
    extractors: dict[str, str]
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    files: tuple[CoverageFile, ...]
    skipped: tuple[Skipped, ...]
    history: History = NOT_COLLECTED
