"""The HTTP bridge: frontend calls linked to backend routes by method and normalized path
(specs/015-http-bridge research R1–R5)."""

from __future__ import annotations

from typing import Any

from graphora.graph.model import Edge, UnresolvedNode

HTTP_VERSION = "0.1.0"
EXTRACTOR = f"http-bridge@{HTTP_VERSION}"


def bridge(py_facts: dict[str, Any], js_facts: dict[str, Any], snapshot: str) -> tuple[list[Edge], list[UnresolvedNode]]:
    """HTTP edges and the unresolved nodes they point to."""
    return [], []
