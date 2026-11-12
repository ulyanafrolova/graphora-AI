"""Read a `.csproj` file as XML data (specs/007-csharp-analysis research.md § R2).

Never runs MSBuild, `dotnet` or NuGet; never follows `<Import>`, never expands `$(…)`, `@(…)` or wildcards, never
reads another file. A `DOCTYPE` (and so any entity declaration) makes the file a parse error, which rules out
entity expansion and external entities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from xml.parsers import expat

ItemKind = Literal["ProjectReference", "PackageReference", "FrameworkReference"]
_ITEMS: tuple[ItemKind, ...] = ("ProjectReference", "PackageReference", "FrameworkReference")
_FLAGS = ("UseWPF", "UseWindowsForms")
_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class Item:
    kind: ItemKind
    include: str  # one entry of `Include`, trimmed, as written
    conditional: bool  # the item or its ItemGroup has a Condition
    line: int
    column: int
    text: str  # the start tag, for the snippet hash


@dataclass(frozen=True)
class ProjectFacts:
    sdk: str | None
    use_wpf: bool
    use_windows_forms: bool
    items: tuple[Item, ...]
    has_error: bool


_ERROR = ProjectFacts(None, False, False, (), True)


class _DoctypeRefused(Exception):
    pass


def _local(name: str) -> str:
    """Element name without an XML namespace (expat reports `uri name` with namespace processing on)."""
    return name.rsplit(" ", 1)[-1]


def read(data: bytes) -> ProjectFacts:
    data = data.removeprefix(_BOM)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _ERROR
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # line numbers as in every other edge (adapters/text.py)
    parser = expat.ParserCreate(namespace_separator=" ")

    def refuse(*_args: object) -> None:
        raise _DoctypeRefused

    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse

    lines = text.split("\n")
    encoded = text.encode("utf-8")
    line_starts = [0]
    for i, byte in enumerate(encoded):
        if byte == 0x0A:
            line_starts.append(i + 1)
    stack: list[tuple[str, bool]] = []  # (element, has Condition)
    items: list[Item] = []
    sdk: list[str | None] = [None]
    flags: dict[str, list[str]] = {name: [] for name in _FLAGS}
    property_text: list[str] = []

    def start(name: str, attrs: dict[str, str]) -> None:
        local = _local(name)
        conditional = "Condition" in attrs
        if not stack and local == "Project":
            sdk[0] = attrs.get("Sdk")
        parent = stack[-1] if stack else None
        if local in _ITEMS and parent is not None and parent[0] == "ItemGroup" and "Include" in attrs:
            conditional = conditional or any(c for _, c in stack)  # ItemGroup, Choose/When, Target
            line = parser.CurrentLineNumber
            # CurrentByteIndex is exact in every expat version; count code points from the line start to it.
            column = len(encoded[line_starts[line - 1] : parser.CurrentByteIndex].decode("utf-8", errors="replace")) + 1
            start_tag = _start_tag(lines, line, column)
            for entry in attrs["Include"].split(";"):
                if entry.strip():
                    items.append(Item(local, entry.strip(), conditional, line, column, start_tag))  # type: ignore[arg-type]
        stack.append((local, conditional))
        property_text.clear()

    def end(name: str) -> None:
        local, _ = stack.pop()
        if local in flags and stack and stack[-1][0] == "PropertyGroup":
            flags[local].append("".join(property_text).strip().lower())
        property_text.clear()

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = property_text.append
    try:
        parser.Parse(encoded, True)
    except (expat.ExpatError, _DoctypeRefused):
        return _ERROR
    return ProjectFacts(sdk[0], "true" in flags["UseWPF"], "true" in flags["UseWindowsForms"], tuple(items), False)


def _start_tag(lines: list[str], line: int, column: int) -> str:
    """The text from `<` to the closing `>` of a start tag, across lines if needed."""
    rest = "\n".join(lines[line - 1 :])
    offset = len(lines[line - 1][: column - 1])
    end = rest.find(">", offset)
    return rest[offset : end + 1] if end != -1 else rest[offset:]
