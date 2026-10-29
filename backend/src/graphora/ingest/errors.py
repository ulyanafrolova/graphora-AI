"""Fetch errors; the CLI maps each to an exit status (specs/002-repo-ingest/data-model.md § Errors)."""

from __future__ import annotations


class IngestError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BadInput(IngestError):
    pass


class UnsafeArchive(IngestError):
    pass


class InvalidArchive(IngestError):
    pass


class RemoteError(IngestError):
    pass
