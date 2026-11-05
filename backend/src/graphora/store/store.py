"""PostgreSQL store of analyses keyed by (repository, snapshot id).

Design: specs/005-storage-http-api/research.md § R1–R8, data-model.md, contracts/store-api.md.

- The graph is kept as the exact serialized bytes; file bytes are kept once per SHA-256 in `blobs`.
- One `Store` holds one connection in autocommit mode. Writes run in an explicit transaction; reads are single
  statements, so each sees one committed state. Every public method holds `self._lock`, so one `Store` can be
  shared by the HTTP server's worker threads (requests are serialized; enough for a local single-user service).
- The graph schema is read from the repository checkout (`schema/graph.schema.json`). The backend runs from the
  checkout via `uv sync`; packaging the schema for a standalone install is left to feature 007.
- Nothing here reads the analyzed project, runs a subprocess, or connects anywhere but the database.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import psycopg
from psycopg import conninfo

from graphora.adapters.text import text_lines
from graphora.graph.build import Analysis, current_extractors
from graphora.graph.serialize import SCHEMA_VERSION, dumps

STORE_VERSION = "1"
MAX_REPOSITORY_LENGTH = 300
_SCHEMA_LOCK = 0x6772617068_6F7261  # advisory lock id for applying schema.sql ("graphora")
_GRAPH_SCHEMA = Path(__file__).resolve().parents[4] / "schema" / "graph.schema.json"

Action = Literal["stored", "replaced", "reused"]


class StoreUnavailable(Exception):
    """The database cannot be reached or has another store version. `reason` never contains a password."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidAnalysis(ValueError):
    """The analysis cannot be stored as given (bad repository name, contents or document)."""


@dataclass(frozen=True)
class StoredAnalysis:
    repository: str
    snapshot: str
    schema_version: int
    extractors: dict[str, str]
    warnings: tuple[str, ...]
    graph: bytes


@dataclass(frozen=True)
class StoreResult:
    action: Action
    analysis: StoredAnalysis


@dataclass(frozen=True)
class FileText:
    path: str
    has_text: bool
    line_count: int
    start: int
    end: int
    lines: tuple[str, ...]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _redact(message: str, url: str) -> str:
    try:
        password = conninfo.conninfo_to_dict(url).get("password")
    except psycopg.Error:
        password = None
    if password:
        message = message.replace(str(password), "***")
    return " ".join(message.split())


def _lock_key(repository: str, snapshot: str) -> int:
    digest = hashlib.sha256(f"{repository}\0{snapshot}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@cache
def _validator():  # type: ignore[no-untyped-def]
    from jsonschema import Draft202012Validator

    return Draft202012Validator(json.loads(_GRAPH_SCHEMA.read_text(encoding="utf-8")))


def _reusable(schema_version: int, extractors: str) -> bool:
    return schema_version == SCHEMA_VERSION and json.loads(extractors) == current_extractors()


class Store:
    def __init__(self, conn: psycopg.Connection, url: str) -> None:
        self._conn = conn
        self._url = url
        self._lock = threading.Lock()

    # -- connection -----------------------------------------------------------------------------------------

    @classmethod
    def open(cls, url: str) -> Store:
        """Connect, apply schema.sql and check the store version."""
        conn = cls._connect(url)
        store = cls(conn, url)
        try:
            with store._guard():
                sql = resources.files("graphora.store").joinpath("schema.sql").read_text(encoding="utf-8")
                with conn.transaction():
                    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK,))
                    conn.execute(sql)  # type: ignore[arg-type]
                row = conn.execute("SELECT value FROM store_meta WHERE key = 'store_version'").fetchone()
            if row is None or row[0] != STORE_VERSION:
                raise StoreUnavailable(f"store version {row[0] if row else 'missing'}, expected {STORE_VERSION}")
        except BaseException:
            conn.close()
            raise
        return store

    @staticmethod
    def _connect(url: str) -> psycopg.Connection:
        try:
            return psycopg.connect(url, autocommit=True, connect_timeout=10)
        except psycopg.Error as exc:
            raise StoreUnavailable(_redact(f"cannot connect: {exc}", url)) from None

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _guard(self) -> Iterator[None]:
        """Turn connection failures into StoreUnavailable; reconnect on the next call after a lost connection."""
        try:
            if self._conn.closed or self._conn.broken:
                self._conn = self._connect(self._url)
            yield
        except psycopg.OperationalError as exc:
            raise StoreUnavailable(_redact(str(exc), self._url)) from None

    # -- writes ---------------------------------------------------------------------------------------------

    def put(self, repository: str, analysis: Analysis) -> StoreResult:
        """Store `analysis` under (repository, its snapshot), reuse a reusable one, or replace a stale one."""
        if not 1 <= len(repository) <= MAX_REPOSITORY_LENGTH:
            raise InvalidAnalysis(f"repository name longer than {MAX_REPOSITORY_LENGTH} characters" if repository else "empty repository name")
        doc = analysis.doc
        data = dumps(doc)
        errors = sorted(_validator().iter_errors(json.loads(data)), key=lambda e: list(e.absolute_path))
        if errors:
            raise InvalidAnalysis(f"graph document does not match the schema: {errors[0].message}")
        rows, blobs = self._file_rows(analysis)
        warnings = _canonical(sorted(analysis.warnings))
        extractors = _canonical(doc.extractors)
        key = (repository, doc.snapshot)

        with self._lock, self._guard():
            conn = self._conn
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (_lock_key(*key),))
                row = conn.execute(
                    "SELECT schema_version, extractors FROM analyses WHERE repository = %s AND snapshot = %s", key
                ).fetchone()
                if row is not None and _reusable(*row):
                    action: Action = "reused"
                else:
                    action = "stored" if row is None else "replaced"
                    if row is not None:
                        conn.execute("DELETE FROM analyses WHERE repository = %s AND snapshot = %s", key)
                    with conn.cursor() as cur:
                        cur.executemany(
                            "INSERT INTO blobs (sha256, content) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            sorted(blobs.items()),
                        )
                        cur.execute(
                            "INSERT INTO analyses (repository, snapshot, schema_version, extractors, warnings, graph,"
                            " graph_sha256) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (*key, SCHEMA_VERSION, extractors, warnings, data, hashlib.sha256(data).hexdigest()),
                        )
                        cur.executemany(
                            "INSERT INTO files (repository, snapshot, path, has_text, line_count, size, sha256)"
                            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            [(*key, *r) for r in rows],
                        )
                stored = self._get_analysis(*key)
        assert stored is not None
        return StoreResult(action, stored)

    @staticmethod
    def _file_rows(analysis: Analysis) -> tuple[list[tuple[Any, ...]], dict[str, bytes]]:
        coverage = {f.path: f for f in analysis.doc.files}
        extra = sorted(set(analysis.contents) - set(coverage))
        if extra:
            raise InvalidAnalysis(f"contents has a path that is not in the coverage report: {extra[0]}")
        rows: list[tuple[Any, ...]] = []
        blobs: dict[str, bytes] = {}
        for path in sorted(coverage):
            data = analysis.contents.get(path)
            if data is None:
                if "unreadable" not in coverage[path].flags:
                    raise InvalidAnalysis(f"contents is missing a readable file: {path}")
                rows.append((path, False, 0, None, None))
                continue
            lines = text_lines(path, data)
            if lines is None:
                rows.append((path, False, 0, len(data), None))
                continue
            digest = hashlib.sha256(data).hexdigest()
            blobs[digest] = data
            rows.append((path, True, len(lines), len(data), digest))
        return rows, blobs

    # -- reads ----------------------------------------------------------------------------------------------

    def _get_analysis(self, repository: str, snapshot: str) -> StoredAnalysis | None:
        row = self._conn.execute(
            "SELECT schema_version, extractors, warnings, graph FROM analyses WHERE repository = %s AND snapshot = %s",
            (repository, snapshot),
        ).fetchone()
        if row is None:
            return None
        schema_version, extractors, warnings, graph = row
        return StoredAnalysis(repository, snapshot, schema_version, json.loads(extractors), tuple(json.loads(warnings)), bytes(graph))

    def get_analysis(self, repository: str, snapshot: str) -> StoredAnalysis | None:
        with self._lock, self._guard():
            return self._get_analysis(repository, snapshot)

    def find_reusable(self, repository: str, snapshot: str) -> StoredAnalysis | None:
        stored = self.get_analysis(repository, snapshot)
        if stored is None or not _reusable(stored.schema_version, _canonical(stored.extractors)):
            return None
        return stored

    def list_repositories(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        with self._lock, self._guard():
            rows = self._conn.execute(
                'SELECT repository, snapshot FROM analyses ORDER BY repository COLLATE "C", snapshot COLLATE "C"'
            ).fetchall()
        grouped: dict[str, list[str]] = {}
        for repository, snapshot in rows:
            grouped.setdefault(repository, []).append(snapshot)
        return tuple((name, tuple(snapshots)) for name, snapshots in grouped.items())

    def has_repository(self, repository: str) -> bool:
        with self._lock, self._guard():
            return self._conn.execute("SELECT 1 FROM analyses WHERE repository = %s LIMIT 1", (repository,)).fetchone() is not None

    def has_snapshot(self, repository: str, snapshot: str) -> bool:
        with self._lock, self._guard():
            return (
                self._conn.execute(
                    "SELECT 1 FROM analyses WHERE repository = %s AND snapshot = %s", (repository, snapshot)
                ).fetchone()
                is not None
            )

    def get_file(
        self, repository: str, snapshot: str, path: str, start: int | None = None, end: int | None = None
    ) -> FileText | None:
        """A file of a stored snapshot, whole or as an inclusive line range; None if not stored.

        Raises ValueError for a range that does not fit the file (contracts/http-api.md)."""
        with self._lock, self._guard():
            row = self._conn.execute(
                "SELECT f.has_text, b.content FROM files f LEFT JOIN blobs b ON b.sha256 = f.sha256"
                " WHERE f.repository = %s AND f.snapshot = %s AND f.path = %s",
                (repository, snapshot, path),
            ).fetchone()
        if row is None:
            return None
        has_text, content = row
        ranged = start is not None or end is not None
        if not has_text:
            if ranged:
                raise ValueError(f"file has no text content: {path}")
            return FileText(path, False, 0, 0, 0, ())
        lines = text_lines(path, bytes(content))
        assert lines is not None  # stored only when it has text
        count = len(lines)
        if count == 0:
            if ranged:
                raise ValueError(f"line range outside the file: {path} has 0 lines")
            return FileText(path, True, 0, 0, 0, ())
        first = 1 if start is None else start
        last = count if end is None else end
        if first < 1:
            raise ValueError("start must be at least 1")
        if last < first:
            raise ValueError("end must not be less than start")
        if first > count:
            raise ValueError(f"line range outside the file: {path} has {count} lines")
        last = min(last, count)
        return FileText(path, True, count, first, last, lines[first - 1 : last])
