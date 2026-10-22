"""Build one GraphDocument from a folder: walk → snapshot → extract → resolve."""

from __future__ import annotations

import io
import tokenize
from pathlib import Path

from graphora.adapters.python import EXTRACTOR
from graphora.adapters.python import VERSION as ADAPTER_VERSION
from graphora.adapters.python.extract import FileFacts, extract
from graphora.detect.languages import classify
from graphora.graph.model import CoverageFile, Edge, ExternalNode, FileNode, GraphDocument, Node, UnresolvedNode
from graphora.graph.serialize import snippet_hash
from graphora.ingest.snapshot import snapshot_id
from graphora.ingest.walk import Deadline, read_file, walk
from graphora.resolve.python import RESOLVER_VERSION, STDLIB_VERSION, build_index, category, resolve


def _decode(data: bytes) -> str | None:
    """Decode by PEP 263 rules without executing anything; None if the file is not valid text."""
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        return data.decode(encoding)
    except (SyntaxError, LookupError, UnicodeDecodeError):
        return None


def build(root: Path, max_files: int, max_bytes: int, deadline: Deadline) -> GraphDocument:
    walked = walk(root, max_files, max_bytes, deadline)
    contents = {path: read_file(root, path) for path in walked.files}
    snapshot = snapshot_id(root, contents, tuple(s.path for s in walked.skipped))

    coverage: list[CoverageFile] = []
    facts: dict[str, FileFacts | None] = {}
    for path in walked.files:
        language, status = classify(path)
        flags: list[str] = []
        if status == "analyzed":
            deadline.check()
            text = _decode(contents[path])
            if text is None:
                flags.append("unreadable")
                facts[path] = None
            else:
                facts[path] = extract(text.encode("utf-8"))
                if facts[path].has_error:
                    flags.append("parse_error")
        coverage.append(CoverageFile(path, language, status, tuple(sorted(flags))))

    index = build_index(sorted(facts))
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    for path, file_facts in sorted(facts.items()):
        node = FileNode(path, file_facts.definitions if file_facts else ())
        nodes[node.id] = node
        for record in file_facts.imports if file_facts else ():
            for target in resolve(path, record, index):
                kind, _, rest = target.node_id.partition(":")
                if kind == "ext":
                    nodes.setdefault(target.node_id, ExternalNode(rest, category(rest)))
                elif kind == "unresolved":
                    nodes.setdefault(target.node_id, UnresolvedNode(rest))
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
                        extractor=EXTRACTOR,
                        snippet_hash=snippet_hash(record.text),
                    )
                )

    return GraphDocument(
        snapshot=snapshot,
        extractors={"python-adapter": ADAPTER_VERSION, "python-resolver": RESOLVER_VERSION, "python-stdlib": STDLIB_VERSION},
        nodes=tuple(nodes.values()),
        edges=tuple(edges),
        files=tuple(coverage),
        skipped=tuple(walked.skipped),
    )
