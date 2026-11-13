"""Error shape and deterministic JSON bodies of the HTTP API (specs/005-storage-http-api/research.md § R11)."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from graphora.pipeline.jobs import QueueFull, Stopping
from graphora.store import StoreUnavailable

log = logging.getLogger("graphora.api")


class ApiError(Exception):
    def __init__(self, kind: str, status: int, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.message = message


def bad_request(message: str) -> ApiError:
    return ApiError("bad_request", 400, message)


def not_found(message: str) -> ApiError:
    return ApiError("not_found", 404, message)


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def json_response(value: Any, status: int = 200) -> Response:
    return Response(json_bytes(value), status_code=status, media_type="application/json")


def _error(kind: str, status: int, message: str) -> Response:
    return json_response({"error": {"kind": kind, "message": message}}, status)


async def _api_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, ApiError)
    return _error(exc.kind, exc.status, exc.message)


async def _validation_error(request: Request, exc: Exception) -> Response:
    return _error("bad_request", 400, "invalid request")  # never echoes the input


async def _http_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code == 404:
        return _error("not_found", 404, "no such endpoint")
    if exc.status_code == 405:
        return _error("method_not_allowed", 405, "method not allowed")
    return _error("bad_request", 400, "invalid request")


async def _queue_full(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, QueueFull)
    return _error("too_many_jobs", 429, str(exc))


async def _stopping(request: Request, exc: Exception) -> Response:
    return _error("stopping", 503, "the service is stopping")


async def _store_unavailable(request: Request, exc: Exception) -> Response:
    log.warning("store unavailable: %s", exc)
    return _error("store_unavailable", 503, "store unavailable")


async def _internal(request: Request, exc: Exception) -> Response:
    log.error("internal error", exc_info=exc)
    return _error("internal", 500, "internal error")


def install(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(QueueFull, _queue_full)
    app.add_exception_handler(Stopping, _stopping)
    app.add_exception_handler(StoreUnavailable, _store_unavailable)
    app.add_exception_handler(Exception, _internal)
