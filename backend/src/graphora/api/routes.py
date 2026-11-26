"""The read-only HTTP API (specs/005-storage-http-api/contracts/http-api.md).

Every handler answers from the store only: no file system reads, no analysis, no writes (FR-015, FR-018).
Handlers are plain `def`: psycopg is synchronous, so FastAPI runs them in its thread pool, and `Store`
serializes access to its connection.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import Response

from graphora.api.errors import ApiError, bad_request, json_response, not_found
from graphora.graph import queries
from graphora.graph.load import loads
from graphora.graph.results import dumps
from graphora.graph.serialize import SCHEMA_VERSION
from graphora.store import Store

_INT = re.compile(r"-?[0-9]{1,9}")


def _params(request: Request, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> dict[str, str]:
    """Exactly the named query parameters, each at most once; anything else is a bad request."""
    allowed = set(required) | set(optional)
    keys = [key for key, _ in request.query_params.multi_items()]
    for key in sorted(set(keys)):
        if key not in allowed:
            raise bad_request(f"unknown parameter: {key}")
        if keys.count(key) > 1:
            raise bad_request(f"parameter given more than once: {key}")
    for key in required:
        if not request.query_params.get(key):
            raise bad_request(f"missing parameter: {key}")
    return {key: request.query_params[key] for key in keys}


def _int(params: dict[str, str], key: str) -> int | None:
    if key not in params:
        return None
    if not _INT.fullmatch(params[key]):
        raise bad_request(f"{key} must be an integer")
    return int(params[key])


def _missing(store: Store, repository: str, snapshot: str) -> Exception:
    if not store.has_repository(repository):
        return not_found(f"repository not found: {repository}")
    return not_found(f"snapshot not found: {repository} {snapshot}")


def stored_index(store: Store, repository: str, snapshot: str) -> queries.GraphIndex:
    """The index of a stored analysis; 404 when it is not stored, 409 when its graph schema is old."""
    stored = store.get_analysis(repository, snapshot)
    if stored is None:
        raise _missing(store, repository, snapshot)
    if stored.schema_version != SCHEMA_VERSION:
        message = f"{stored.repository} {stored.snapshot} was analyzed with graph schema {stored.schema_version}"
        raise ApiError("stale", 409, message + "; analyze it again")
    return queries.index(loads(stored.graph))


def router(store: Store) -> APIRouter:
    api = APIRouter(prefix="/api/v1")

    @api.get("/repositories")
    def repositories(request: Request) -> Response:
        _params(request, ())
        listed = [{"name": name, "snapshots": list(snapshots)} for name, snapshots in store.list_repositories()]
        return json_response({"repositories": listed})

    @api.get("/graph")
    def graph(request: Request) -> Response:
        params = _params(request, ("repository", "snapshot"))
        stored = store.get_analysis(params["repository"], params["snapshot"])
        if stored is None:
            raise _missing(store, params["repository"], params["snapshot"])
        return Response(stored.graph, media_type="application/json")

    @api.get("/hotspots")
    def hotspots(request: Request) -> Response:
        params = _params(request, ("repository", "snapshot"), ("limit", "include_type_only"))
        limit = 10 if "limit" not in params else _int(params, "limit")
        flag = params.get("include_type_only", "true")
        if flag not in ("true", "false"):
            raise bad_request("include_type_only must be true or false")
        ix = stored_index(store, params["repository"], params["snapshot"])
        try:
            answer = queries.hotspots(ix, include_type_only=flag == "true", limit=limit)
        except ValueError as exc:
            raise bad_request(str(exc)) from None
        return Response(dumps(answer), media_type="application/json")

    @api.get("/file")
    def file(request: Request) -> Response:
        params = _params(request, ("repository", "snapshot", "path"), ("start", "end"))
        start, end = _int(params, "start"), _int(params, "end")
        repository, snapshot, path = params["repository"], params["snapshot"], params["path"]
        try:
            found = store.get_file(repository, snapshot, path, start, end)
        except ValueError as exc:
            raise bad_request(str(exc)) from None
        if found is None:
            if not store.has_snapshot(repository, snapshot):
                raise _missing(store, repository, snapshot)
            raise not_found(f"path not found in snapshot: {path}")
        return json_response(
            {
                "path": found.path,
                "has_text": found.has_text,
                "line_count": found.line_count,
                "start": found.start,
                "end": found.end,
                "lines": [{"n": found.start + i, "text": text} for i, text in enumerate(found.lines)],
            }
        )

    return api
