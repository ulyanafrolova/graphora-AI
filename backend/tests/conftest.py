from __future__ import annotations

import io
import json
import socket
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "fixtures" / "repos"
SCHEMA_PATH = REPO_ROOT / "schema" / "graph.schema.json"


def _deny_network(*args: object, **kwargs: object) -> None:
    raise AssertionError("network access in tests")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that opens a network connection (002 research § R10, FR-019)."""
    monkeypatch.setattr(socket.socket, "connect", _deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny_network)
    monkeypatch.setattr(socket, "create_connection", _deny_network)


def run_analyze(directory: Path | str, *args: str) -> tuple[int, bytes, str]:
    """Run `graphora analyze` in-process and capture stdout bytes and stderr text."""
    from graphora.cli import main

    out_buf, err_buf = io.BytesIO(), io.StringIO()
    out = io.TextIOWrapper(out_buf, encoding="utf-8", newline="")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err_buf
    try:
        code = main(["analyze", str(directory), *args])
    finally:
        out.flush()
        sys.stdout, sys.stderr = old_out, old_err
    return code, out_buf.getvalue(), err_buf.getvalue()


def _snapshot_kind(snapshot: str) -> str:
    if snapshot.startswith("content:"):
        return "content"
    return "dirty" if "+dirty:" in snapshot else "sha"


def edge_key(e: dict[str, Any]) -> tuple[str, int, str, str, str, str]:
    return (e["source"], e["line"], e["target"], e["symbol"] or "", e.get("alias") or "", e["type"])


def project(doc: dict[str, Any], sections: set[str]) -> dict[str, Any]:
    """Reduce a graph document to the hand-checkable shape used by expected.json (001 research § R10, 003 § R9)."""
    out: dict[str, Any] = {}
    if "nodes" in sections:
        nodes = []
        for n in doc["nodes"]:
            item = {"id": n["id"], "kind": n["kind"]}
            if n["kind"] == "external":
                item["category"] = n["category"]
            if n["kind"] in ("external", "unresolved"):
                item["ecosystem"] = n["ecosystem"]
            if n["kind"] == "asset":
                item["path"] = n["path"]
            if n["kind"] == "file":
                item["language"] = n["language"]
                item["definitions"] = n["definitions"]
                if "exports" in n:
                    item["exports"] = n["exports"]
            nodes.append(item)
        out["nodes"] = sorted(nodes, key=lambda n: n["id"])
    if "edges" in sections:
        edges = []
        for e in doc["edges"]:
            item = {
                "source": e["source"],
                "target": e["target"],
                "type": e["type"],
                "form": e["form"],
                "symbol": e["symbol"],
                "line": e["line"],
                "confidence": e["confidence"],
                "reason": e.get("reason"),
            }
            if e["type_only"]:
                item["type_only"] = True
            if "alias" in e:
                item["alias"] = e["alias"]
            edges.append(item)
        out["edges"] = sorted(edges, key=edge_key)
    if "coverage" in sections:
        out["coverage"] = doc["coverage"]["files"]
    if "skipped" in sections:
        out["skipped"] = doc["coverage"]["skipped"]
    if "snapshot_kind" in sections:
        out["snapshot_kind"] = _snapshot_kind(doc["snapshot"])
    return out


@pytest.fixture(scope="session")
def validator():
    from jsonschema import Draft202012Validator

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)
