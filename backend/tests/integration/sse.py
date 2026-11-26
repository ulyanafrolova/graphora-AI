"""Reading a `text/event-stream` body in tests (specs/013-ask-sse tasks T001)."""

from __future__ import annotations

from collections.abc import Iterable


def read_stream(lines: Iterable[str]) -> list[tuple[str, str | None, str]]:
    """(event, id, data) per message, in order; a keep-alive comment is ("ping", None, "")."""
    out: list[tuple[str, str | None, str]] = []
    event, ident, data = None, None, []
    for line in lines:
        if line == "":
            if event is not None or data:
                out.append((event or "message", ident, "\n".join(data)))
            event, ident, data = None, None, []
        elif line.startswith(":"):
            out.append(("ping", None, ""))
        elif line.startswith("event: "):
            event = line[len("event: ") :]
        elif line.startswith("id: "):
            ident = line[len("id: ") :]
        elif line.startswith("data: "):
            data.append(line[len("data: ") :])
    if event is not None or data:
        out.append((event or "message", ident, "\n".join(data)))
    return out


def messages(stream: list[tuple[str, str | None, str]]) -> list[tuple[str, str | None, str]]:
    return [m for m in stream if m[0] != "ping"]
