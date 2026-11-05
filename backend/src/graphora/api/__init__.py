"""Read-only HTTP API over the analysis store (specs/005-storage-http-api/contracts/http-api.md)."""

from __future__ import annotations

from fastapi import FastAPI

from graphora.api import errors
from graphora.api.routes import router
from graphora.store import Store


def create_app(store: Store) -> FastAPI:
    app = FastAPI(title="Graphora", version="0.1.0", openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs", redoc_url=None)
    errors.install(app)
    app.include_router(router(store))
    return app
