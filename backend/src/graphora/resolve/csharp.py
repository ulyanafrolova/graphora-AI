"""Resolve C# `using` directives to the files that declare the named namespace or type, to .NET base-library
namespaces, or to NuGet packages. Rules: specs/007-csharp-analysis/data-model.md § Resolution, research R4–R6.

Never guesses: several possible targets give several `heuristic` edges with a reason, or one `unresolved` edge.
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path, PurePosixPath

from graphora.adapters.csharp.extract import CsFacts, UsingRecord
from graphora.adapters.msbuild.csproj import Item, ProjectFacts

RESOLVER_VERSION = "0.1.0"
NAMESPACES_VERSION = "10.0.0"
NETCORE = "Microsoft.NETCore.App"
ASPNETCORE = "Microsoft.AspNetCore.App"
WINDOWSDESKTOP = "Microsoft.WindowsDesktop.App"
_WEB_SDKS = frozenset({"Microsoft.NET.Sdk.Web", "Microsoft.NET.Sdk.Razor", "Microsoft.NET.Sdk.BlazorWebAssembly"})
_MSBUILD_SYNTAX = ("$(", "@(", "*", "?")
_DATA = Path(__file__).with_name("data") / "dotnet_namespaces.txt"


@cache
def framework_namespaces() -> Mapping[str, frozenset[str]]:
    """Shared framework name → its namespaces, from the shipped list (research R6)."""
    out: dict[str, set[str]] = {}
    for line in _DATA.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            framework, namespace = line.split(" ", 1)
            out.setdefault(framework, set()).add(namespace)
    return {k: frozenset(v) for k, v in sorted(out.items())}


def namespaces_for(frameworks: Iterable[str]) -> frozenset[str]:
    table = framework_namespaces()
    return frozenset().union(*(table.get(f, frozenset()) for f in sorted(set(frameworks))))


# --- ownership --------------------------------------------------------------------------------------------------


def owner(path: str, csproj_by_folder: Mapping[str, tuple[str, ...]]) -> tuple[str | None, bool]:
    """The `.csproj` that owns a `.cs` file: the first folder upwards that holds `.csproj` files (research R3).

    Returns (project path or None, ambiguous). Two or more `.csproj` in that folder → (None, True)."""
    folder = PurePosixPath(path).parent
    while True:
        key = "" if str(folder) == "." else str(folder)
        found = csproj_by_folder.get(key)
        if found:
            return (found[0], False) if len(found) == 1 else (None, True)
        if key == "":
            return None, False
        folder = folder.parent


def csproj_folders(paths: Iterable[str]) -> dict[str, tuple[str, ...]]:
    out: dict[str, list[str]] = {}
    for p in sorted(paths):
        parent = str(PurePosixPath(p).parent)
        out.setdefault("" if parent == "." else parent, []).append(p)
    return {k: tuple(v) for k, v in out.items()}


# --- index ------------------------------------------------------------------------------------------------------


@dataclass
class Scope:
    """The declarations of one project, or of the project-less files (key "")."""

    key: str
    namespaces: dict[str, tuple[str, ...]] = field(default_factory=dict)  # namespace → files with types directly in it
    types: dict[str, tuple[str, ...]] = field(default_factory=dict)  # full type name → declaring files
    declared: frozenset[str] = frozenset()  # every declared namespace and each of its parent namespaces


def build_scopes(facts: Mapping[str, CsFacts | None], owners: Mapping[str, str | None]) -> dict[str, Scope]:
    """One scope per project key (`owners[path]`, "" when project-less), with sorted file tuples."""
    namespaces: dict[str, dict[str, set[str]]] = {}
    types: dict[str, dict[str, set[str]]] = {}
    declared: dict[str, set[str]] = {}
    for path in sorted(facts):
        key = owners.get(path) or ""
        namespaces.setdefault(key, {})
        types.setdefault(key, {})
        declared.setdefault(key, set())
        file_facts = facts[path]
        if file_facts is None:
            continue
        for ns in file_facts.namespaces:
            parts = ns.split(".")
            declared[key].update(".".join(parts[: i + 1]) for i in range(len(parts)))
        for t in file_facts.types:
            types[key].setdefault(t.name, set()).add(path)
            if t.namespace:
                namespaces[key].setdefault(t.namespace, set()).add(path)
    return {
        key: Scope(
            key,
            {n: tuple(sorted(f)) for n, f in sorted(namespaces[key].items())},
            {n: tuple(sorted(f)) for n, f in sorted(types[key].items())},
            frozenset(declared[key]),
        )
        for key in sorted(namespaces)
    }


# --- resolution -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    node_id: str  # file:…, ext:dotnet:…, ext:nuget:…, unresolved:dotnet:…
    symbol: str
    confidence: str
    reason: str | None


@dataclass(frozen=True)
class Context:
    """What one file can see. `visible` lists (scope key, reachable only through a conditional reference)."""

    visible: tuple[tuple[str, bool], ...]
    frameworks: frozenset[str]  # base-library namespaces of the file's project
    packages: Mapping[str, str] = field(default_factory=dict)  # lower-case package id → node spelling


_PRIORITY = ("partial_type", "namespace_spread", "package_prefix", "msbuild_condition")


def _reason(*reasons: str | None) -> str | None:
    present = [r for r in reasons if r]
    return min(present, key=_PRIORITY.index) if present else None


def candidates(record: UsingRecord) -> tuple[str, ...]:
    """Names to try, innermost first: inside namespace `A.B`, `X` is tried as `A.B.X`, `A.X`, `X` (research R5)."""
    name = record.target or ""
    if record.rooted or record.global_using or not record.namespace:
        return (name,)
    parts = record.namespace.split(".")
    return tuple(".".join(parts[:i] + [name]) for i in range(len(parts), 0, -1)) + (name,)


class Resolver:
    def __init__(self, scopes: Mapping[str, Scope]) -> None:
        self.scopes = scopes
        self._all_namespaces = frozenset(n for s in scopes.values() for n in s.namespaces)
        self._all_types = frozenset(t for s in scopes.values() for t in s.types)
        self._all_declared = frozenset(n for s in scopes.values() for n in s.declared)

    def _files(self, table: str, name: str, ctx: Context) -> dict[str, bool]:
        """Declaring files visible to `ctx` → reachable only through a conditional reference."""
        out: dict[str, bool] = {}
        for key, conditional in ctx.visible:
            scope = self.scopes.get(key)
            for f in getattr(scope, table).get(name, ()) if scope else ():
                out[f] = out.get(f, True) and conditional
        return out

    def _visible_declared(self, name: str, ctx: Context) -> bool:
        return any(name in self.scopes[k].declared for k, _ in ctx.visible if k in self.scopes)

    def _edges(self, path: str, symbol: str, files: dict[str, bool], spread_reason: str) -> list[Target]:
        others = {f: c for f, c in sorted(files.items()) if f != path}
        spread = spread_reason if len(files) > 1 else None
        out = []
        for f, conditional in others.items():
            reason = _reason(spread, "msbuild_condition" if conditional else None)
            out.append(Target(f"file:{f}", symbol, "heuristic" if reason else "resolved", reason))
        return out

    def resolve(self, path: str, record: UsingRecord, ctx: Context) -> list[Target]:
        """Targets of one directive; [] when it names only the file itself or aliases a non-name type."""
        if record.target is None:
            return []
        names = candidates(record)
        want_types = record.form in ("using_static", "using_alias")
        want_namespaces = record.form in ("using", "using_alias")
        for name in names:
            if want_types:
                files = self._files("types", name, ctx)
                if files:
                    return self._edges(path, name, files, "partial_type")
            if want_namespaces:
                files = self._files("namespaces", name, ctx)
                if files:
                    return self._edges(path, name, files, "namespace_spread")
                if self._visible_declared(name, ctx):
                    return [Target(f"unresolved:dotnet:{name}", name, "unresolved", "no_types")]
        for name in names:
            if (want_types and name in self._all_types) or (
                want_namespaces and (name in self._all_namespaces or name in self._all_declared)
            ):
                return [Target(f"unresolved:dotnet:{name}", name, "unresolved", "not_referenced")]

        written = names[-1]
        library_names = ([written] if want_namespaces else []) + ([written.rpartition(".")[0]] if want_types else [])
        for name in library_names:
            if name and name in ctx.frameworks:
                return [Target(f"ext:dotnet:{name}", name, "resolved", None)]
        lowered = written.lower()
        matches = sorted(p for p in ctx.packages if lowered == p or lowered.startswith(p + "."))
        if len(matches) == 1:
            spelling = ctx.packages[matches[0]]
            return [Target(f"ext:nuget:{spelling}", written, "heuristic", "package_prefix")]
        if matches:
            return [Target(f"unresolved:dotnet:{written}", written, "unresolved", "ambiguous")]
        return [Target(f"unresolved:dotnet:{written}", written, "unresolved", "not_found")]


# --- projects (data-model.md § ProjectReference, § PackageReference; research R4) ---------------------------------


def _condition(conditional: bool) -> tuple[str, str | None]:
    return ("heuristic", "msbuild_condition") if conditional else ("resolved", None)


def resolve_project_reference(project: str, item: Item, projects: frozenset[str]) -> Target:
    include = item.include
    if any(token in include for token in _MSBUILD_SYNTAX):
        return Target(f"unresolved:dotnet:{include}", include, "unresolved", "msbuild_property")
    relative = include.replace("\\", "/")
    if relative.startswith("/") or (len(relative) > 1 and relative[1] == ":"):
        return Target(f"unresolved:dotnet:{include}", include, "unresolved", "not_found")
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(project), relative))
    if joined == ".." or joined.startswith("../"):
        return Target(f"unresolved:dotnet:{include}", include, "unresolved", "not_found")
    if joined in projects:
        confidence, reason = _condition(item.conditional)
        return Target(f"project:{joined}", include, confidence, reason)
    return Target(f"unresolved:dotnet:{joined}", include, "unresolved", "not_found")


def resolve_package_reference(item: Item, spellings: Mapping[str, str]) -> Target:
    include = item.include
    if "$(" in include or "@(" in include:
        return Target(f"unresolved:dotnet:{include}", include, "unresolved", "msbuild_property")
    confidence, reason = _condition(item.conditional)
    return Target(f"ext:nuget:{spellings[include.lower()]}", include, confidence, reason)


class Projects:
    """Project references, visibility, frameworks and packages of every walked `.csproj` (sorted throughout)."""

    def __init__(self, facts: Mapping[str, ProjectFacts]) -> None:
        self.facts = dict(sorted(facts.items()))
        self.paths = frozenset(self.facts)
        self.spellings: dict[str, str] = {}
        for p in self.facts:
            for item in self.facts[p].items:
                if item.kind == "PackageReference" and "$(" not in item.include and "@(" not in item.include:
                    self.spellings.setdefault(item.include.lower(), item.include)
        self.references: dict[str, list[Target]] = {}
        self.packages: dict[str, list[Target]] = {}
        for p, f in self.facts.items():
            self.references[p] = [resolve_project_reference(p, i, self.paths) for i in f.items if i.kind == "ProjectReference"]
            self.packages[p] = [resolve_package_reference(i, self.spellings) for i in f.items if i.kind == "PackageReference"]

    def _reach(self, start: str, unconditional_only: bool) -> set[str]:
        seen, todo = {start}, [start]
        while todo:
            for t in self.references.get(todo.pop(), ()):
                if not t.node_id.startswith("project:") or (unconditional_only and t.confidence != "resolved"):
                    continue
                target = t.node_id.removeprefix("project:")
                if target not in seen:
                    seen.add(target)
                    todo.append(target)
        return seen

    def context(self, project: str | None) -> Context:
        """What a file owned by `project` (None: project-less or ambiguous) can see."""
        if project is None or project not in self.facts:
            return Context(visible=(("", False),), frameworks=namespaces_for([NETCORE]))
        firm = self._reach(project, True)
        every = self._reach(project, False)
        visible = ((project, False),) + tuple((p, p not in firm) for p in sorted(every - {project}))
        f = self.facts[project]
        frameworks = [NETCORE]
        framework_refs = {i.include for i in f.items if i.kind == "FrameworkReference"}
        if f.sdk in _WEB_SDKS or ASPNETCORE in framework_refs:
            frameworks.append(ASPNETCORE)
        if f.use_wpf or f.use_windows_forms or WINDOWSDESKTOP in framework_refs:
            frameworks.append(WINDOWSDESKTOP)
        packages = {
            t.symbol.lower(): t.node_id.removeprefix("ext:nuget:") for t in self.packages[project] if t.node_id.startswith("ext:nuget:")
        }
        return Context(visible=visible, frameworks=namespaces_for(frameworks), packages=dict(sorted(packages.items())))
