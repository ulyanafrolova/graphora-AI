"""HTTP API over the analysis store (specs/005-storage-http-api/contracts/http-api.md), plus analysis jobs
(specs/010-end-to-end-pipeline/contracts/http-api.md) when a job runner is given."""

from __future__ import annotations

from fastapi import FastAPI

from graphora.api import errors
from graphora.api import jobs
from graphora.api.routes import router
from graphora.pipeline.jobs import JobRunner
from graphora.store import Store


def create_app(store: Store, runner: JobRunner | None = None) -> FastAPI:
    app = FastAPI(title="Graphora", version="0.1.0", openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs", redoc_url=None)
    errors.install(app)
    app.include_router(router(store))
    if runner is not None:
        app.include_router(jobs.router(runner))
    return app
