"""Canonical serialization of a GraphDocument (research.md § R4, § R7)."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from graphora.graph.model import Edge, ExternalNode, FileNode, GraphDocument, Node

SCHEMA_VERSION = 1


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def snippet_hash(text: str) -> str:
    """Hash of the import text with whitespace runs collapsed, so reformatting keeps it stable."""
    return "sha256:" + _sha16(" ".join(text.split()))


def edge_id(edge: Edge) -> str:
    return "e:" + _sha16(f"{edge.source}|{edge.line}|{edge.column}|{edge.target}|{edge.symbol or ''}")


def edge_sort_key(edge: Edge) -> tuple[str, int, int, str, str]:
    return (edge.source, edge.line, edge.column, edge.target, edge.symbol or "")


def _node_dict(node: Node) -> dict[str, Any]:
    if isinstance(node, FileNode):
        definitions = sorted(node.definitions, key=lambda d: (d.line, d.name))
        return {
            "id": node.id,
            "kind": "file",
            "path": node.path,
            "language": "python",
            "definitions": [{"kind": d.kind, "name": d.name, "line": d.line} for d in definitions],
        }
    if isinstance(node, ExternalNode):
        return {"id": node.id, "kind": "external", "name": node.name, "category": node.category}
    return {"id": node.id, "kind": "unresolved", "reference": node.reference}


def _edge_dict(edge: Edge) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": edge_id(edge),
        "source": edge.source,
        "target": edge.target,
        "type": "imports",
        "symbol": edge.symbol,
        "line": edge.line,
        "column": edge.column,
        "snapshot": edge.snapshot,
        "confidence": edge.confidence,
        "extractor": edge.extractor,
        "snippet_hash": edge.snippet_hash,
    }
    if edge.reason is not None:
        out["reason"] = edge.reason
    return out


def to_dict(doc: GraphDocument) -> dict[str, Any]:
    files = sorted(doc.files, key=lambda f: f.path)
    skipped = sorted(doc.skipped, key=lambda s: s.path)
    statuses = Counter(f.status for f in files)
    languages = Counter(f.language for f in files if f.language is not None)
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot": doc.snapshot,
        "extractors": dict(doc.extractors),
        "nodes": [_node_dict(n) for n in sorted(doc.nodes, key=lambda n: n.id)],
        "edges": [_edge_dict(e) for e in sorted(doc.edges, key=edge_sort_key)],
        "coverage": {
            "files": [
                {"path": f.path, "language": f.language, "status": f.status, "flags": sorted(f.flags)}
                for f in files
            ],
            "skipped": [{"path": s.path, "reason": s.reason} for s in skipped],
            "summary": {
                "analyzed": statuses["analyzed"],
                "detected_only": statuses["detected_only"],
                "not_code": statuses["not_code"],
                "skipped": len(skipped),
                "by_language": dict(sorted(languages.items())),
            },
        },
    }


def dumps(doc: GraphDocument) -> bytes:
    text = json.dumps(to_dict(doc), sort_keys=True, ensure_ascii=False, indent=2)
    return (text + "\n").encode("utf-8")
