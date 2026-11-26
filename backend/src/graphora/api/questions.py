"""Graph questions over HTTP, one route per question (specs/018-http-queries/contracts/http-api.md)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from graphora.api.errors import bad_request, not_found
from graphora.api.routes import _INT, _params, stored_index
from graphora.graph import queries
from graphora.graph.results import dumps
from graphora.store import Store

DEFAULT_LIMIT, MAX_LIMIT = 50, 500
BOOLEANS = {"include_type_only": True, "follow_barrels": False}
LEVELS = ("file", "project")


@dataclass(frozen=True)
class Question:
    name: str
    ask: Callable
    target: str | None
    options: tuple[str, ...]
    default_limit: int | None


QUESTIONS: tuple[Question, ...] = ()


def _allowed(row: Question) -> tuple[tuple[str, ...], tuple[str, ...]]:
    required = ("repository", "snapshot") + ((row.target,) if row.target else ())
    return required, row.options + (("limit",) if row.default_limit is not None else ())


def _integer(params: dict[str, str], key: str) -> int | None:
    if key not in params:
        return None
    if not _INT.fullmatch(params[key]):
        raise bad_request(f"{key} must be an integer")
    return int(params[key])


def _option(params: dict[str, str], key: str) -> Any:
    if key in BOOLEANS:
        if key not in params:
            return BOOLEANS[key]
        if params[key] not in ("true", "false"):
            raise bad_request(f"{key} must be true or false")
        return params[key] == "true"
    if key == "level":
        level = params.get(key, "file")
        if level not in LEVELS:
            raise bad_request("level must be file or project")
        return level
    if key == "symbol":
        if key in params and not params[key]:
            raise bad_request("symbol must not be empty")
        return params.get(key)
    return _integer(params, key)


def _arguments(row: Question, params: dict[str, str]) -> tuple[tuple[str, ...], dict[str, Any]]:
    """The positional target and keyword options of `row.ask`, from already checked parameter names."""
    options = {key: _option(params, key) for key in row.options}
    if row.default_limit is not None:
        limit = _integer(params, "limit")
        if limit is None:
            limit = row.default_limit
        if not 0 <= limit <= MAX_LIMIT:
            raise bad_request(f"limit must be between 0 and {MAX_LIMIT}")
        options["limit"] = limit
    return ((params[row.target],) if row.target else ()), options


def _openapi(row: Question) -> list[dict[str, Any]]:
    required, optional = _allowed(row)
    schemas: dict[str, dict[str, Any]] = {
        "include_type_only": {"type": "boolean", "default": True},
        "follow_barrels": {"type": "boolean", "default": False},
        "level": {"type": "string", "enum": list(LEVELS), "default": "file"},
        "symbol": {"type": "string"},
        "max_depth": {"type": "integer", "minimum": 1},
        "limit": {"type": "integer", "minimum": 0, "maximum": MAX_LIMIT, "default": row.default_limit},
    }
    return [{"name": key, "in": "query", "required": True, "schema": {"type": "string"}} for key in required] + [
        {"name": key, "in": "query", "required": False, "schema": schemas[key]} for key in optional
    ]


def _endpoint(store: Store, row: Question) -> Callable[[Request], Response]:
    def answer(request: Request) -> Response:
        params = _params(request, *_allowed(row))
        target, options = _arguments(row, params)
        ix = stored_index(store, params["repository"], params["snapshot"])
        try:
            result = row.ask(ix, *target, **options)
        except queries.NodeNotFound as exc:
            raise (bad_request if exc.status == "invalid_path" else not_found)(exc.message) from None
        except ValueError as exc:
            raise bad_request(str(exc)) from None
        return Response(dumps(result), media_type="application/json")

    return answer


def router(store: Store) -> APIRouter:
    api = APIRouter(prefix="/api/v1")
    for row in sorted(QUESTIONS, key=lambda q: q.name):
        api.add_api_route(
            f"/{row.name}", _endpoint(store, row), methods=["GET"], name=row.name, openapi_extra={"parameters": _openapi(row)}
        )
    return api
