"""HTTP API over the analysis store (specs/005-storage-http-api/contracts/http-api.md), plus analysis jobs
(specs/010-end-to-end-pipeline/contracts/http-api.md) when a job runner is given and questions to the agents
(specs/013-ask-sse/contracts/http-api.md) when an ask service is given, and graph questions
(specs/018-http-queries/contracts/http-api.md); with a built UI folder, the UI too (specs/019-frontend research § R7)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from graphora.api import errors
from graphora.api import jobs
from graphora.api import questions
from graphora.api.routes import router
from graphora.pipeline.jobs import JobRunner
from graphora.store import Store

if TYPE_CHECKING:
    from graphora.api.ask import AskService


CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "connect-src 'self'"
)


def _serve_ui(app: FastAPI, ui: Path) -> None:
    """Files of the built UI, `index.html` for client routes; nothing outside `ui`, never under /api/."""
    root = ui.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def page(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise StarletteHTTPException(404)
        found = (root / path).resolve()
        if not found.is_relative_to(root) or not found.is_file():
            found = root / "index.html"
        return FileResponse(found, headers={"Content-Security-Policy": CSP})


def create_app(
    store: Store, runner: JobRunner | None = None, asks: AskService | None = None, ui: Path | None = None
) -> FastAPI:
    app = FastAPI(title="Graphora", version="0.1.0", openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs", redoc_url=None)
    errors.install(app)
    app.include_router(router(store, runner, asks))
    app.include_router(questions.router(store))
    if runner is not None:
        app.include_router(jobs.router(runner))
    if asks is not None:
        from graphora.api import ask

        app.include_router(ask.router(asks))
    if ui is not None:
        _serve_ui(app, ui)
    return app
