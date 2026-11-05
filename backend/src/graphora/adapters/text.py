"""Source decoding and line splitting shared by the adapters and the store (005 research § R5).

Line N here is line N in every edge: lines end at `\\n`, `\\r\\n` or a lone `\\r` (see `position.py`), and never
at the other characters `str.splitlines` treats as line breaks (form feed, `\\u2028`, ...).
"""

from __future__ import annotations

import io
import re
import tokenize

_LINE_END = re.compile(r"\r\n|\r|\n")


def decode_python(data: bytes) -> str | None:
    """Decode by PEP 263 rules without executing anything; None if the file is not valid text.

    A UTF-8 BOM is removed (the detected encoding is then `utf-8-sig`)."""
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        return data.decode(encoding)
    except (SyntaxError, LookupError, UnicodeDecodeError):
        return None


def decode(path: str, data: bytes) -> str | None:
    """The text of a file as the analysis sees it, or None for binary or undecodable content.

    `.py` files follow PEP 263; every other file must be strict UTF-8. A NUL byte means binary."""
    if b"\x00" in data:
        return None
    if path.endswith(".py"):
        return decode_python(data)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def split_lines(text: str) -> tuple[str, ...]:
    """Lines without their endings. A final line ending adds no empty line; "" has no lines."""
    if not text:
        return ()
    lines = _LINE_END.split(text)
    if lines[-1] == "":
        lines.pop()
    return tuple(lines)


def text_lines(path: str, data: bytes) -> tuple[str, ...] | None:
    """Decoded lines of a file, with a leading BOM removed from line 1; None if the file has no text."""
    text = decode(path, data)
    if text is None:
        return None
    return split_lines(text.removeprefix("﻿"))
