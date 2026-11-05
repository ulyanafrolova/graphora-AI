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
    """The suite runs offline (002 research § R10)."""
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


def run_query(*args: str) -> tuple[int, bytes, str]:
    """Run `graphora query` in-process and capture stdout bytes and stderr text."""
    from graphora.cli import main

    out_buf, err_buf = io.BytesIO(), io.StringIO()
    out = io.TextIOWrapper(out_buf, encoding="utf-8", newline="")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err_buf
    try:
        code = main(["query", *args])
    finally:
        out.flush()
        sys.stdout, sys.stderr = old_out, old_err
    return code, out_buf.getvalue(), err_buf.getvalue()


_ANALYZED: dict[str, bytes] = {}


def analyzed_graph(name: str) -> bytes:
    """The graph document `graphora analyze` writes for a fixture, cached for the session (004 tasks T002)."""
    if name not in _ANALYZED:
        code, out, err = run_analyze(FIXTURES / name / "repo")
        assert code == 0, err
        _ANALYZED[name] = out
    return _ANALYZED[name]


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


# --- 005 analysis store (specs/005-storage-http-api/research.md § R12) -------------------------------------

DEFAULT_LIMITS = (5000, 50 * 1024 * 1024)


@pytest.fixture(scope="session")
def database_url() -> str:
    import os

    url = os.environ.get("GRAPHORA_TEST_DATABASE_URL")
    if not url:
        pytest.fail(
            "GRAPHORA_TEST_DATABASE_URL is not set: run `make db` and export "
            "GRAPHORA_TEST_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora_test, "
            "or deselect store tests with -m 'not db'",
            pytrace=False,
        )
    return url


@pytest.fixture
def store(database_url):
    """An empty store. psycopg's libpq connects outside Python's `socket`, so `_no_network` stays on."""
    from graphora.store import Store

    s = Store.open(database_url)
    s._conn.execute("TRUNCATE files, analyses, blobs")
    yield s
    s.close()


def analyze_fixture(name: str):
    return analyze_dir(FIXTURES / name / "repo")


def analyze_dir(root: Path):
    from graphora.graph.build import analyze
    from graphora.ingest.walk import Deadline

    return analyze(root, *DEFAULT_LIMITS, Deadline(300))
