"""Build one GraphDocument from a folder: walk → snapshot → extract → resolve, per language."""

from __future__ import annotations

import io
import tokenize
from pathlib import Path

from graphora.adapters import js, python
from graphora.adapters.js import extract as js_extract
from graphora.adapters.python import extract as py_extract
from graphora.detect.languages import classify
from graphora.graph.model import (
    AssetNode,
    CoverageFile,
    Edge,
    ExternalNode,
    FileNode,
    GraphDocument,
    Node,
    UnresolvedNode,
)
from graphora.graph.serialize import snippet_hash
from graphora.ingest.snapshot import snapshot_id
from graphora.ingest.walk import Deadline, read_file, walk
from graphora.resolve import js as js_resolve
from graphora.resolve import python as py_resolve
from graphora.resolve.tsconfig import load_configs


def _decode(data: bytes) -> str | None:
    """Decode by PEP 263 rules without executing anything; None if the file is not valid text."""
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        return data.decode(encoding)
    except (SyntaxError, LookupError, UnicodeDecodeError):
        return None


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


def build(root: Path, max_files: int, max_bytes: int, deadline: Deadline) -> tuple[GraphDocument, tuple[str, ...]]:
    """The graph document, plus warnings: config files that could not be read (contracts/cli.md)."""
    walked = walk(root, max_files, max_bytes, deadline)
    contents = {path: read_file(root, path) for path in walked.files}
    snapshot = snapshot_id(root, contents, tuple(s.path for s in walked.skipped))
    files = frozenset(walked.files)
    configs = load_configs(files, contents.__getitem__)
    invalid_configs = frozenset(configs.invalid)

    coverage: list[CoverageFile] = []
    py_facts: dict[str, py_extract.FileFacts | None] = {}
    js_facts: dict[str, js_extract.FileFacts | None] = {}
    languages: dict[str, str] = {}
    for path in walked.files:
        language, status = classify(path)
        flags: list[str] = []
        if status == "analyzed":
            deadline.check()
            languages[path] = language
            if language == "python":
                text = _decode(contents[path])
                facts = py_extract.extract(text.encode("utf-8")) if text is not None else None
                py_facts[path] = facts
            else:
                facts = js_extract.extract(path, contents[path])
                js_facts[path] = facts
            if facts is None:
                flags.append("unreadable")
            elif facts.has_error:
                flags.append("parse_error")
        if path in invalid_configs:
            flags.append("parse_error")
        coverage.append(CoverageFile(path, language, status, tuple(sorted(flags))))

    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    _python_graph(py_facts, snapshot, nodes, edges)
    resolver = js_resolve.JsResolver(files, frozenset(languages), configs, js_resolve.workspace_names(files, contents.__getitem__))
    _js_graph(js_facts, languages, resolver, snapshot, nodes, edges)

    doc = GraphDocument(
        snapshot=snapshot,
        extractors={
            "js-adapter": js.VERSION,
            "js-resolver": js_resolve.RESOLVER_VERSION,
            "node-builtins": js_resolve.BUILTINS_VERSION,
            "python-adapter": python.VERSION,
            "python-resolver": py_resolve.RESOLVER_VERSION,
            "python-stdlib": py_resolve.STDLIB_VERSION,
        },
        nodes=tuple(nodes.values()),
        edges=tuple(edges),
        files=tuple(coverage),
        skipped=tuple(walked.skipped),
    )
    return doc, configs.invalid
