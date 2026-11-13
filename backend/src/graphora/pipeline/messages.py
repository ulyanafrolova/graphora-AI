"""Limit messages shared by the CLI and the HTTP API (specs/010-end-to-end-pipeline research § R11).

The CLI names a limit by its option (`--max-files`), the API by its key (`max_files`); the reason is the same.
"""

from __future__ import annotations

from typing import Literal

from graphora.ingest.walk import LimitExceeded

_TEMPLATES = {
    "files": "file limit exceeded: at least {observed} files > {name} {value}",
    "bytes": "size limit exceeded: at least {observed} bytes > {name} {value}",
    "seconds": "time limit exceeded: {observed}s > {name} {value}",
    "archive_bytes": "archive size limit exceeded: at least {observed} bytes > {name} {value}",
    "extract_bytes": "extracted size limit exceeded: at least {observed} bytes > {name} {value}",
    "entries": "entry limit exceeded: at least {observed} entries > {name} {value}",
}


def limit_key(limit: str) -> str:
    """`files` → `max_files`: the limit's name in the API and in `PipelineLimits`."""
    return f"max_{limit}"


def limit_message(exc: LimitExceeded, style: Literal["cli", "api"]) -> str:
    key = limit_key(exc.limit)
    name = "--" + key.replace("_", "-") if style == "cli" else key
    return _TEMPLATES[exc.limit].format(observed=exc.observed, name=name, value=exc.value)
