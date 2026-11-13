"""Job endpoints: start an analysis and read its status (specs/010-end-to-end-pipeline contracts/http-api.md).

Input is checked here, before a job exists (FR-004, research § R9). Only a GitHub link reaches
`parse_source`, so the server never looks at its own file system for a client value (FR-003).
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from graphora.api.errors import bad_request, not_found
from graphora.api.routes import _params
from graphora.ingest.errors import BadInput
from graphora.ingest.source import GitHubSource, parse_source
from graphora.pipeline import LIMIT_KEYS, PipelineLimits
from graphora.pipeline.jobs import JobRunner, JobStatus

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_BODY_KEYS = ("github", "ref", "limits")


def _accepted(status: JobStatus) -> Response:
    return Response(status.to_json(), status_code=202, media_type="application/json")


def _limit_value(key: str, value: Any, server: float) -> float:
    whole = isinstance(value, int) and not isinstance(value, bool)
    number = whole or (key == "max_seconds" and isinstance(value, float))
    if not number or not 1 <= value <= server:
        kind = "a number" if key == "max_seconds" else "an integer"
        raise bad_request(f"invalid limit {key}: must be {kind} from 1 to {server:g}")
    return value


def parse_limits(given: dict[str, Any], server: PipelineLimits) -> PipelineLimits:
    """Client limits may only lower the server's limits (FR-015)."""
    values = server.as_dict()
    for key in sorted(given):
        if key not in LIMIT_KEYS:
            raise bad_request(f"unknown limit: {key}")
        values[key] = _limit_value(key, given[key], values[key])
    return PipelineLimits(**values)


def parse_github(body: dict[str, Any]) -> GitHubSource:
    link, ref = body.get("github"), body.get("ref")
    if not isinstance(link, str) or not link:
        raise bad_request("missing github: a GitHub repository link")
    if ref is not None and not isinstance(ref, str):
        raise bad_request("ref must be a string")
    if not _SCHEME.match(link):
        raise bad_request(f"not a GitHub repository link: {link}")
    try:
        source = parse_source(link, ref)
    except BadInput as exc:
        raise bad_request(exc.message.replace("--ref", "ref")) from None
    assert isinstance(source, GitHubSource)  # a value with a scheme is parsed as a link or rejected
    return source


def router(runner: JobRunner) -> APIRouter:
    api = APIRouter(prefix="/api/v1")

    @api.post("/jobs")
    async def start_github(request: Request) -> Response:
        _params(request, ())
        try:
            body = json.loads(await request.body())
        except (ValueError, UnicodeDecodeError):
            raise bad_request("the body must be a JSON object") from None
        if not isinstance(body, dict):
            raise bad_request("the body must be a JSON object")
        for key in sorted(body):
            if key not in _BODY_KEYS:
                raise bad_request(f"unknown key: {key}")
        limits_given = body.get("limits", {})
        if not isinstance(limits_given, dict):
            raise bad_request("limits must be a JSON object")
        source = parse_github(body)
        limits = parse_limits(limits_given, runner.limits)
        return _accepted(runner.submit_github(source, limits))

    @api.get("/jobs/{job_id}")
    def job(job_id: str, request: Request) -> Response:
        _params(request, ())
        status = runner.status(job_id)
        if status is None:
            raise not_found(f"job not found: {job_id}")
        return Response(status.to_json(), media_type="application/json")

    return api
