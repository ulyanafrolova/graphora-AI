"""Graph questions over HTTP, one route per question (specs/018-http-queries/contracts/http-api.md)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter

from graphora.store import Store

DEFAULT_LIMIT, MAX_LIMIT = 50, 500


@dataclass(frozen=True)
class Question:
    name: str
    ask: Callable
    target: str | None
    options: tuple[str, ...]
    default_limit: int | None


QUESTIONS: tuple[Question, ...] = ()


def router(store: Store) -> APIRouter:
    api = APIRouter(prefix="/api/v1")
    return api
