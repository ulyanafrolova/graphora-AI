"""Build one GraphDocument from a folder: walk → snapshot → extract → resolve, per language."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

from graphora.adapters import csharp, js, msbuild, python
from graphora.adapters.csharp import extract as cs_extract
from graphora.adapters.msbuild import csproj
from graphora.adapters.js import extract as js_extract
from graphora.adapters.python import extract as py_extract
from graphora.adapters.text import decode_python as _decode
from graphora.detect.languages import classify
from graphora.graph.model import (
    AssetNode,
    CoverageFile,
    Edge,
    ExternalNode,
    FileNode,
    GraphDocument,
    Node,
    ProjectNode,
    UnresolvedNode,
)
from graphora.graph.serialize import snippet_hash
from graphora.ingest.snapshot import snapshot_id
from graphora.ingest.walk import Deadline, read_file, walk
from graphora.resolve import csharp as cs_resolve
from graphora.resolve import js as js_resolve
from graphora.resolve import python as py_resolve
from graphora.resolve.tsconfig import load_configs


@dataclass(frozen=True)
class Analysis:
    """One analysis run: the document, its warnings, and the exact bytes read for each readable walked file
    (specs/005-storage-http-api/research.md § R4). Files that could not be opened have no entry."""

    doc: GraphDocument
    warnings: tuple[str, ...]
    contents: Mapping[str, bytes]


def current_extractors() -> dict[str, str]:
    """The extractor versions this code writes into every document (005 research § R6)."""
    return {
        "csproj-reader": msbuild.VERSION,
        "csharp-adapter": csharp.VERSION,
        "csharp-resolver": cs_resolve.RESOLVER_VERSION,
        "dotnet-namespaces": cs_resolve.NAMESPACES_VERSION,
        "dotnet-types": cs_resolve.TYPES_VERSION,
        "js-adapter": js.VERSION,
        "js-resolver": js_resolve.RESOLVER_VERSION,
        "node-builtins": js_resolve.BUILTINS_VERSION,
        "python-adapter": python.VERSION,
        "python-resolver": py_resolve.RESOLVER_VERSION,
        "python-stdlib": py_resolve.STDLIB_VERSION,
    }


def _python_graph(facts: dict[str, py_extract.FileFacts | None], snapshot: str, nodes: dict[str, Node], edges: list[Edge]) -> None:
    index = py_resolve.build_index(sorted(facts))
    for path, file_facts in sorted(facts.items()):
        node = FileNode(path, "python", file_facts.definitions if file_facts else ())
        nodes[node.id] = node
        for record in file_facts.imports if file_facts else ():
            for target in py_resolve.resolve(path, record, index):
                kind, _, rest = target.node_id.partition(":")
                rest = rest.removeprefix("python:")
                if kind == "ext":
                    nodes.setdefault(target.node_id, ExternalNode(rest, "python", py_resolve.category(rest)))
                elif kind == "unresolved":
                    nodes.setdefault(target.node_id, UnresolvedNode(rest, "python"))
                edges.append(
                    Edge(
                        source=node.id,
                        target=target.node_id,
                        symbol=target.symbol,
                        line=record.line,
                        column=record.column,
                        snapshot=snapshot,
                        confidence="unresolved" if target.reason else "resolved",
                        reason=target.reason,
                        extractor=python.EXTRACTOR,
                        snippet_hash=snippet_hash(record.text),
                        form="dynamic" if record.kind == "dynamic" else "static",
                    )
                )


def _js_graph(
    facts: dict[str, js_extract.FileFacts | None],
    languages: dict[str, str],
    resolver: js_resolve.JsResolver,
    snapshot: str,
    nodes: dict[str, Node],
    edges: list[Edge],
) -> None:
    for path, file_facts in sorted(facts.items()):
        node = FileNode(path, languages[path], file_facts.definitions if file_facts else (), file_facts.exports if file_facts else ())
        nodes[node.id] = node
        for record in file_facts.imports if file_facts else ():
            target, reason = resolver.resolve(path, record)
            kind, _, rest = target.partition(":")
            if kind == "ext":
                name = rest.removeprefix("npm:")
                nodes.setdefault(target, ExternalNode(name, "npm", js_resolve.category(name)))
            elif kind == "unresolved":
                nodes.setdefault(target, UnresolvedNode(rest.removeprefix("npm:"), "npm"))
            elif kind == "asset":
                nodes.setdefault(target, AssetNode(rest))
            for name in record.names:
                edges.append(
                    Edge(
                        source=node.id,
                        target=target,
                        symbol=name.symbol,
                        line=record.line,
                        column=record.column,
                        snapshot=snapshot,
                        confidence="unresolved" if reason else "resolved",
                        reason=reason,
                        extractor=js.EXTRACTOR,
                        snippet_hash=snippet_hash(record.text),
                        type=record.edge_type,
                        form=record.form,
                        type_only=name.type_only,
                        alias=name.alias,
                    )
                )


def _node_for(target: str) -> Node | None:
    """The external or placeholder node a C# target id stands for; None for file targets."""
    kind, _, rest = target.partition(":")
    ecosystem, _, name = rest.partition(":")
    if kind == "ext":
        return ExternalNode(name, ecosystem, "stdlib" if ecosystem == "dotnet" else "third_party")
    if kind == "unresolved":
        return UnresolvedNode(name, ecosystem)
    return None


def _project_graph(projects: cs_resolve.Projects, snapshot: str, nodes: dict[str, Node], edges: list[Edge]) -> None:
    """Project nodes and their reference edges (specs/007-csharp-analysis data-model.md § Project reference edge)."""
    for path, project_facts in projects.facts.items():
        node = ProjectNode(path)
        nodes[node.id] = node
        for item in project_facts.items:
            if item.kind == "ProjectReference":
                target = cs_resolve.resolve_project_reference(path, item, projects.paths)
                edge_type = "project_reference"
            elif item.kind == "PackageReference":
                target = cs_resolve.resolve_package_reference(item, projects.spellings)
                edge_type = "package_reference"
            else:
                continue
            extra = _node_for(target.node_id)
            if extra is not None:
                nodes.setdefault(extra.id, extra)
            edges.append(
                Edge(
                    source=node.id,
                    target=target.node_id,
                    symbol=target.symbol,
                    line=item.line,
                    column=item.column,
                    snapshot=snapshot,
                    confidence=target.confidence,
                    reason=target.reason,
                    extractor=msbuild.EXTRACTOR,
                    snippet_hash=snippet_hash(item.text),
                    type=edge_type,
                )
            )


_RANK = {"resolved": 0, "heuristic": 1, "unresolved": 2}


def _csharp_graph(
    facts: dict[str, cs_extract.CsFacts | None],
    owners: dict[str, str | None],
    projects: cs_resolve.Projects,
    snapshot: str,
    nodes: dict[str, Node],
    edges: list[Edge],
) -> dict[str, int]:
    """File nodes, `using` edges (007 data-model.md) and `type_reference` edges (008 data-model.md).

    Returns the number of unresolved type names per file, for the coverage report."""
    scopes = cs_resolve.build_scopes(facts, owners)
    resolver = cs_resolve.Resolver(scopes)
    types = cs_resolve.TypeResolver(resolver)
    contexts: dict[str | None, cs_resolve.Context] = {}
    for project in sorted({owners.get(p) for p in facts}, key=lambda p: p or ""):
        contexts[project] = projects.context(project)

    # Pass 1: type references. Which directives were used decides the `using` fallback in pass 2 (008 R7).
    used: set[str] = set()
    references: dict[str, dict[str, tuple[int, int, int, cs_resolve.Target, str]]] = {}
    unresolved_names: dict[str, int] = {}
    for path, file_facts in sorted(facts.items()):
        if file_facts is None:
            unresolved_names[path] = 0
            continue
        ctx = contexts[owners.get(path)]
        usings = cs_resolve.FileUsings(path, file_facts.usings)
        best: dict[str, tuple[int, int, int, cs_resolve.Target, str]] = {}
        missing: set[str] = set()
        for ref in file_facts.type_refs:
            result = types.resolve(path, ref, ctx, usings)
            if not result.found:
                if ref.kind != "qualifier":
                    missing.add(ref.name)
                continue
            if any(t.node_id.startswith("file:") for t in result.targets) or not result.targets:
                used.update(result.via)
            for target in result.targets:
                key = (_RANK[target.confidence], ref.line, ref.column)
                if target.node_id not in best or key < best[target.node_id][:3]:
                    best[target.node_id] = (*key, target, ref.text)
        references[path] = best
        unresolved_names[path] = len(missing)

    # Pass 2: nodes and edges.
    for path, file_facts in sorted(facts.items()):
        project = owners.get(path)
        node = FileNode(path, "csharp", file_facts.definitions if file_facts else (), None, f"project:{project}" if project else None)
        nodes[node.id] = node
        ctx = contexts[project]
        for record in file_facts.usings if file_facts else ():
            drop_files = record.form != "using_static" and cs_resolve.directive_id(path, record) in used
            for target in resolver.resolve(path, record, ctx):
                if drop_files and target.node_id.startswith("file:"):
                    continue  # the types used through this directive have their own edges
                extra = _node_for(target.node_id)
                if extra is not None:
                    nodes.setdefault(extra.id, extra)
                edges.append(
                    Edge(
                        source=node.id,
                        target=target.node_id,
                        symbol=target.symbol,
                        line=record.line,
                        column=record.column,
                        snapshot=snapshot,
                        confidence=target.confidence,
                        reason=target.reason,
                        extractor=csharp.EXTRACTOR,
                        snippet_hash=snippet_hash(record.text),
                        alias=record.alias,
                        directive=record.form,
                        global_using=record.global_using,
                    )
                )
        for target_id, (_, line, column, target, text) in sorted(references.get(path, {}).items()):
            extra = _node_for(target_id)
            if extra is not None:
                nodes.setdefault(extra.id, extra)
            edges.append(
                Edge(
                    source=node.id,
                    target=target_id,
                    symbol=target.symbol,
                    line=line,
                    column=column,
                    snapshot=snapshot,
                    confidence=target.confidence,
                    reason=target.reason,
                    extractor=csharp.EXTRACTOR,
                    snippet_hash=snippet_hash(text),
                    type="type_reference",
                )
            )
    return unresolved_names


def build(
    root: Path, max_files: int, max_bytes: int, deadline: Deadline, snapshot: str | None = None
) -> tuple[GraphDocument, tuple[str, ...]]:
    """The graph document, plus warnings: config files that could not be read (contracts/cli.md).

    A given `snapshot` (e.g. the commit SHA of a fetched tarball) is used as is (specs/002-repo-ingest FR-014).
    """
    result = analyze(root, max_files, max_bytes, deadline, snapshot)
    return result.doc, result.warnings


def analyze(root: Path, max_files: int, max_bytes: int, deadline: Deadline, snapshot: str | None = None) -> Analysis:
    """`build()` plus the bytes it read, so a store keeps exactly what was analyzed."""
    walked = walk(root, max_files, max_bytes, deadline)
    contents: dict[str, bytes] = {}
    for path in walked.files:
        if path in walked.special:
            continue  # not a regular file: listed as `unreadable`, never opened
        try:
            contents[path] = read_file(root, path)
        except OSError:
            pass  # e.g. no read permission: listed as `unreadable`, left out of the content hash
    if snapshot is None:
        snapshot = snapshot_id(root, contents, tuple(s.path for s in walked.skipped))
    files = frozenset(walked.files)
    read = lambda path: contents.get(path, b"")  # an unreadable config or package.json reads as empty
    configs = load_configs(files, read)
    invalid_configs = frozenset(configs.invalid)

    csproj_paths = sorted(p for p in walked.files if p.lower().endswith(".csproj"))
    csproj_folders = cs_resolve.csproj_folders(csproj_paths)
    csproj_facts = {p: csproj.read(contents[p]) for p in csproj_paths if p in contents}
    broken_csproj = frozenset(p for p, f in csproj_facts.items() if f.has_error)
    cs_owners: dict[str, str | None] = {}

    coverage: list[CoverageFile] = []
    cs_facts: dict[str, cs_extract.CsFacts | None] = {}
    py_facts: dict[str, py_extract.FileFacts | None] = {}
    js_facts: dict[str, js_extract.FileFacts | None] = {}
    languages: dict[str, str] = {}
    for path in walked.files:
        language, status = classify(path)
        flags: list[str] = []
        if status == "analyzed":
            deadline.check()
            languages[path] = language
            data = contents.get(path)
            if language == "python":
                text = _decode(data) if data is not None else None
                facts = py_extract.extract(text.encode("utf-8"), deadline.check) if text is not None else None
                py_facts[path] = facts
            elif language == "csharp":
                facts = cs_extract.extract(data, deadline.check) if data is not None else None
                cs_facts[path] = facts
                cs_owners[path], is_ambiguous = cs_resolve.owner(path, csproj_folders)
                if is_ambiguous:
                    flags.append("ambiguous_project")
            else:
                facts = js_extract.extract(path, data, deadline.check) if data is not None else None
                js_facts[path] = facts
            if facts is None:
                flags.append("unreadable")
            elif facts.has_error:
                flags.append("parse_error")
        elif path not in contents:
            flags.append("unreadable")
        if path in invalid_configs or path in broken_csproj:
            flags.append("parse_error")
        coverage.append(CoverageFile(path, language, status, tuple(sorted(flags))))

    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    _python_graph(py_facts, snapshot, nodes, edges)
    resolver = js_resolve.JsResolver(files, frozenset(languages), configs, js_resolve.workspace_names(files, read))
    _js_graph(js_facts, languages, resolver, snapshot, nodes, edges)
    projects = cs_resolve.Projects(csproj_facts)
    _project_graph(projects, snapshot, nodes, edges)
    unresolved_names = _csharp_graph(cs_facts, cs_owners, projects, snapshot, nodes, edges)
    coverage = [replace(c, unresolved_type_names=unresolved_names[c.path]) if c.path in unresolved_names else c for c in coverage]

    doc = GraphDocument(
        snapshot=snapshot,
        extractors=current_extractors(),
        nodes=tuple(nodes.values()),
        # `import os, os.path` or `from m import f, f` repeat one fact; keeping both would repeat an edge id
        edges=tuple(dict.fromkeys(edges)),
        files=tuple(coverage),
        skipped=tuple(walked.skipped),
    )
    warnings = tuple(sorted(set(configs.invalid) | broken_csproj))
    return Analysis(doc, warnings, MappingProxyType(contents))
