"""Read `.sln` (text) and `.slnx` (XML) solution files as data (specs/009-csharp-solutions-project-views research
§ R1, R2). Never runs `dotnet sln`, MSBuild or anything named in the file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.parsers import expat

NAME = "sln-reader"
VERSION = "0.1.0"
EXTRACTOR = f"{NAME}@{VERSION}"

SOLUTION_FOLDER = "2150E333-8FDC-42A3-9474-1A3956D46DE8"
_HEADER = "Microsoft Visual Studio Solution File"
_PROJECT = re.compile(r'^(\s*)Project\("\{([0-9A-Fa-f-]+)\}"\)\s*=\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"[^"]*"')
_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class SolutionEntry:
    path: str  # as written
    line: int
    column: int
    text: str  # the entry, for the snippet hash


@dataclass(frozen=True)
class SolutionFacts:
    entries: tuple[SolutionEntry, ...]
    has_error: bool


_ERROR = SolutionFacts((), True)


def _text(data: bytes) -> str | None:
    try:
        text = data.removeprefix(_BOM).decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_sln(data: bytes) -> SolutionFacts:
    """`Project("{TYPE}") = "Name", "Path", "{GUID}"` lines; solution folders skipped (research R1)."""
    text = _text(data)
    if text is None:
        return _ERROR
    lines = text.split("\n")
    if not any(line.strip().startswith(_HEADER) for line in lines[:3]):
        return _ERROR
    entries = []
    for number, line in enumerate(lines, start=1):
        match = _PROJECT.match(line)
        if match is None or match.group(2).upper() == SOLUTION_FOLDER:
            continue
        entries.append(SolutionEntry(match.group(4).strip(), number, len(match.group(1)) + 1, line.strip()))
    return SolutionFacts(tuple(entries), False)


class _Refused(Exception):
    pass


def read_slnx(data: bytes) -> SolutionFacts:
    """Every `Project Path="…"` element; folders and solution items create nothing (research R2)."""
    text = _text(data)
    if text is None:
        return _ERROR
    encoded = text.encode("utf-8")
    line_starts = [0] + [i + 1 for i, b in enumerate(encoded) if b == 0x0A]
    lines = text.split("\n")
    parser = expat.ParserCreate()
    entries: list[SolutionEntry] = []

    def refuse(*_args: object) -> None:
        raise _Refused

    def start(tag: str, attrs: dict[str, str]) -> None:
        if tag == "Project" and attrs.get("Path", "").strip():
            line = parser.CurrentLineNumber
            column = len(encoded[line_starts[line - 1] : parser.CurrentByteIndex].decode("utf-8", errors="replace")) + 1
            rest = "\n".join(lines[line - 1 :])[column - 1 :]
            end = rest.find(">")
            entries.append(SolutionEntry(attrs["Path"].strip(), line, column, rest[: end + 1] if end != -1 else rest))

    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    parser.StartElementHandler = start
    try:
        parser.Parse(encoded, True)
    except (expat.ExpatError, _Refused):
        return _ERROR
    return SolutionFacts(tuple(entries), False)


def read(path: str, data: bytes) -> SolutionFacts:
    return read_slnx(data) if path.lower().endswith(".slnx") else read_sln(data)
